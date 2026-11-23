"""Read local evidence and resolve stable references without executing content."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


MAX_FILE_BYTES = 1024 * 1024
MAX_ARTIFACTS = 64
NAME = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
ARTIFACT_NAME = re.compile(NAME)
LINE_REF = re.compile(rf"artifact:({NAME})#L([1-9][0-9]*)-L([1-9][0-9]*)")
JSON_REF = re.compile(rf"artifact:({NAME}):(/.*)")
PACKET_REF = re.compile(r"packet:/observations/(0|[1-9][0-9]*)(/.*)?")
ORIGIN_REF = "packet:/authorized_origin"
ARRAY_INDEX = re.compile(r"0|[1-9][0-9]*")


def _read_text(path):
    # The nonblocking open also prevents a swapped-in FIFO from hanging the runner.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Evidence files must be regular local files.")
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Evidence files must be regular local files.")
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("An evidence file exceeds the size limit.")
    return data.decode("utf-8-sig")


def _unique_members(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON member in supplied evidence.")
        result[name] = value
    return result


def _reject_constant(_token):
    raise ValueError("Invalid JSON constant in supplied evidence.")


def _parse_json(text):
    return json.loads(text, object_pairs_hook=_unique_members, parse_constant=_reject_constant)


def _pointer(parts):
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _segments(pointer):
    if pointer is None or pointer == "":
        return ()
    if not isinstance(pointer, str) or not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise ValueError("Invalid JSON pointer.")
    return tuple(part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/"))


def _at(value, parts):
    for part in parts:
        if isinstance(value, dict):
            value = value[part]
        elif isinstance(value, list) and ARRAY_INDEX.fullmatch(part):
            value = value[int(part)]
        else:
            raise KeyError(part)
    return value


def _local_path(value):
    if isinstance(value, str) and urlsplit(value).scheme in {"http", "https", "file"}:
        raise ValueError("Supply a local filesystem path.")
    return Path(value)


def is_evidence_ref(ref):
    return any(pattern.fullmatch(ref) for pattern in (PACKET_REF, JSON_REF, LINE_REF))


class EvidenceBundle:
    """A collector packet and up to 64 named UTF-8 artifacts, each at most 1 MiB."""

    def __init__(self, packet=None):
        if packet is not None and not isinstance(packet, dict):
            raise ValueError("The collector packet must be a JSON object.")
        self._packet = deepcopy(packet)
        self._artifacts = {}
        self._json = {}

    @classmethod
    def from_directory(cls, directory, *, packet_path=None):
        directory = _local_path(directory)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Supply a local evidence directory.")
        candidates = sorted(path for path in directory.iterdir() if path.name != "case.json")
        packet_file = _local_path(packet_path) if packet_path is not None else None
        default_packet = directory / "packet.json"
        if packet_file is None and default_packet in candidates:
            packet_file = default_packet
        packet = None if packet_file is None else _parse_json(_read_text(packet_file))
        if packet_file is not None and not isinstance(packet, dict):
            raise ValueError("The collector packet must be a JSON object.")
        bundle = cls(packet)
        candidates = [path for path in candidates if path != default_packet and
                      (packet_file is None or path.absolute() != packet_file.absolute())]
        if len(candidates) > MAX_ARTIFACTS:
            raise ValueError("The evidence directory contains too many artifacts.")
        for path in candidates:
            if not ARTIFACT_NAME.fullmatch(path.name):
                raise ValueError("An artifact has an unsupported name.")
            content = _read_text(path)
            bundle._artifacts[path.name] = content
            if path.suffix.lower() == ".json":
                try:
                    bundle._json[path.name] = _parse_json(content)
                except (ValueError, RecursionError):
                    # A malformed export can still provide literal text evidence.
                    pass
        return bundle

    @property
    def packet(self):
        return deepcopy(self._packet)

    @property
    def artifact_names(self):
        return tuple(self._artifacts)

    def artifact_text(self, name):
        return self._artifacts[name]

    @staticmethod
    def packet_ref(index, *parts):
        return "packet:" + _pointer(("observations", index, *parts))

    @staticmethod
    def artifact_ref(name, *parts):
        if not parts:
            raise ValueError("Supply at least one JSON pointer segment.")
        return f"artifact:{name}:" + _pointer(parts)

    @staticmethod
    def line_ref(name, first, last):
        return f"artifact:{name}#L{first}-L{last}"

    def resolve(self, ref):
        """Return a JSON value or text lines, or raise for an invalid locator."""
        if ref == ORIGIN_REF:
            return (self._packet or {})["authorized_origin"]
        if match := PACKET_REF.fullmatch(ref):
            index, pointer = match.groups()
            return deepcopy(_at(self._packet, ("observations", index, *_segments(pointer))))
        if match := JSON_REF.fullmatch(ref):
            name, pointer = match.groups()
            return deepcopy(_at(self._json[name], _segments(pointer)))
        if match := LINE_REF.fullmatch(ref):
            name, first, last = match.groups()
            first, last = int(first), int(last)
            lines = self._artifacts[name].splitlines()
            if first <= last <= len(lines):
                return "\n".join(lines[first - 1:last])
        raise KeyError(ref)

    def resolves(self, ref):
        try:
            self.resolve(ref)
        except (TypeError, ValueError, LookupError):
            return False
        return True

    def _observation(self, index):
        observations = (self._packet or {}).get("observations")
        if not isinstance(observations, list):
            return None
        try:
            observation = observations[int(index)]
        except (ValueError, IndexError):
            return None
        return observation if isinstance(observation, dict) else None

    def supports(self, ref):
        """Check that a reference can support a structural decision."""
        if not self.resolves(ref):
            return False
        match = PACKET_REF.fullmatch(ref)
        if not match:
            return ref != ORIGIN_REF
        observation = self._observation(match[1])
        return (observation is not None and observation.get("status") == "observed"
                and _field_observed(observation, _segments(match[2])))

    def has_need(self, need):
        """Check whether the named artifact or observed phase supplies a need."""
        parts = _segments(need.pointer)
        if need.kind == "artifact":
            if not parts:
                return bool(self._artifacts.get(need.name, "").strip())
            sources = (self._json.get(need.name),)
        else:
            observations = (self._packet or {}).get("observations")
            if not isinstance(observations, list):
                return False
            sources = (row for row in observations if isinstance(row, dict)
                       and row.get("phase") == need.name and row.get("status") == "observed"
                       and _field_observed(row, parts))
        for source in sources:
            try:
                if _at(source, parts) is not None:
                    return True
            except (LookupError, ValueError):
                continue
        return False


def _field_observed(row, parts):
    if not parts:
        return True
    field, *rest = parts
    if field in {"forms", "notices"}:
        return row.get("document_evidence_status") == "observed"
    if field == "page_status":
        return row.get("page_response_evidence_status") == "observed"
    if field == "storage":
        status = row.get("storage_evidence_status")
        keys = rest[:1] or ["cookies", "local", "session"]
        return isinstance(status, dict) and all(status.get(key) == "observed" for key in keys)
    if field == "requests" and len(rest) > 1 and rest[1] in {"status", "response_evidence_status"}:
        try:
            return _at(row, ("requests", rest[0], "response_evidence_status")) == "observed"
        except (LookupError, ValueError):
            return False
    return True
