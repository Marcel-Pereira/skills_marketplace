const filters = document.getElementById("dashboard-filters");
const search = document.getElementById("skill-search");
const suggestions = document.getElementById("skill-suggestions");
const addSkill = document.getElementById("add-skill");
const skills = Array.from(filters.querySelectorAll('input[name="skill"]'));

function optionLabel(skill) {
  return `${skill.dataset.skillName} (${skill.dataset.categoryName})`;
}

for (const skill of skills) {
  const option = document.createElement("option");
  option.value = optionLabel(skill);
  suggestions.append(option);
}
addSkill.disabled = false;
document.getElementById("skill-search-controls").hidden = false;

// A page restored with Back can still hold the edits that submitted the next search.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) filters.reset();
});

filters.addEventListener("submit", (event) => {
  if (event.submitter !== addSkill) return;

  const query = search.value.trim().toLowerCase();
  let matches = skills.filter((skill) => optionLabel(skill).toLowerCase() === query);
  if (!matches.length) {
    matches = skills.filter((skill) => skill.dataset.skillName.toLowerCase() === query);
  }
  if (matches.length === 1) {
    matches[0].checked = true;
    return;
  }

  event.preventDefault();
  const message = matches.length ? "Choose the skill with its category." : "Choose a skill from the list.";
  search.setCustomValidity(message);
  search.reportValidity();
  search.setCustomValidity("");
});
