// Skill pickers (onboarding and profile): typing a skill and pressing Enter adds it
// as a new, already selected chip, so people can add skills that aren't in our list.
// A page can have several pickers, so each one gets its own listener.
document.querySelectorAll(".chip-picker").forEach(function (picker) {
  const input = picker.querySelector(".custom-skill");
  const chips = picker.querySelector(".chips");

  input.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") return;
    event.preventDefault(); // otherwise Enter would submit the whole form

    const skill = input.value.trim();
    if (!skill) return;

    // Build the same markup as a chip in _macros.html
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = input.dataset.name; // "learns" or "teaches", set by the macro
    checkbox.value = skill;
    checkbox.checked = true;

    const label = document.createElement("label");
    label.className = "chip";
    label.append(checkbox, skill);
    chips.append(label);

    input.value = "";
  });
});
