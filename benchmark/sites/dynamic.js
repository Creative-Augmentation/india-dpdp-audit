"use strict";

const shell = document.querySelector("#contact-shell");
const notice = document.createElement("p");
notice.id = "collection-notice";
notice.textContent = "The synthetic reference field represents a request for a reply.";

const form = document.createElement("form");
form.setAttribute("aria-describedby", notice.id);
form.addEventListener("submit", (event) => event.preventDefault());

const label = document.createElement("label");
label.textContent = "Synthetic reference ";
const field = document.createElement("input");
field.name = "fixture-reference";
field.placeholder = "DEMO-REFERENCE";
field.required = true;
label.append(field);
form.append(label);
shell.append(notice, form);
