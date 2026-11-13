// Each direction keeps its own search. Hidden checked boxes still submit with the form.
for (const editor of document.querySelectorAll('.profile-editor')) {
  const search = editor.querySelector('input[type="search"]');
  const groups = [...editor.querySelectorAll('details.category')];
  const empty = editor.querySelector('[role="status"]');
  let previouslyOpen = null;

  function filterSkills() {
    const term = search.value.trim().toLowerCase();
    if (term && previouslyOpen === null) {
      previouslyOpen = new Set(groups.filter(group => group.open));
    }
    let anyMatch = false;
    for (const group of groups) {
      const categoryMatches = group.querySelector('summary').textContent.toLowerCase().includes(term);
      let groupMatches = false;
      for (const chip of group.querySelectorAll('label.chip')) {
        const matches = categoryMatches || chip.textContent.toLowerCase().includes(term);
        chip.hidden = !matches;
        if (matches) groupMatches = true;
      }
      group.hidden = !groupMatches;
      if (term) group.open = groupMatches;
      else if (previouslyOpen !== null) group.open = previouslyOpen.has(group);
      if (groupMatches) anyMatch = true;
    }
    if (!term) previouslyOpen = null;
    empty.hidden = !term || anyMatch;
  }

  search.addEventListener('input', filterSkills);
  search.addEventListener('keydown', event => {
    if (event.key === 'Enter') event.preventDefault();
  });
  editor.querySelector('.profile-search').hidden = false;
}
