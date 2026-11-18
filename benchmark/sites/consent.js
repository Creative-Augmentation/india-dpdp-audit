"use strict";

const fixture = document.querySelector("[data-consent-fixture]").dataset.consentFixture;
const choiceKey = `dpdp-fixture-choice-${fixture}`;
const indicator = document.querySelector("#choice");

function showChoice() {
  indicator.textContent = localStorage.getItem(choiceKey) ?? "unset";
}

function sendOptionalEvent(event) {
  const query = new URLSearchParams({ source: fixture, event });
  void fetch(`/events/optional?${query}`, { cache: "no-store" });
}

showChoice();
if (fixture === "early" || localStorage.getItem(choiceKey) === "granted") {
  sendOptionalEvent("load");
}

for (const button of document.querySelectorAll("[data-choice]")) {
  button.addEventListener("click", () => {
    const choice = button.dataset.choice;
    if (choice === "reset") {
      localStorage.removeItem(choiceKey);
      showChoice();
      return;
    }
    localStorage.setItem(choiceKey, choice);
    showChoice();
    if (choice === "granted") {
      sendOptionalEvent("accept");
    }
  });
}
