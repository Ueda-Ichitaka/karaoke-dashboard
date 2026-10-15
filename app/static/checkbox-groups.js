// A checkbox group with one "nothing special" choice (the trait group's
// "None", marked data-exclusive-choice="none" on the admin edit forms):
// checking any other box unchecks it, checking it unchecks all others, and
// unchecking the last other box checks it again. Loaded on every page from
// base.html; under node it only exports exclusiveChoice() for the tests
// (tests/test_checkbox_groups.py). The server applies the same rule on save
// (app/traits.py: format_traits).
(function () {
  "use strict";

  // boxes: the group's checkboxes ({value, checked}) right after a click on
  // `changed`; updates their checked state in place.
  function exclusiveChoice(boxes, changed, exclusive) {
    const exclusiveBox = boxes.find((b) => b.value === exclusive);
    if (!exclusiveBox) return;
    if (changed === exclusiveBox) {
      if (changed.checked) boxes.forEach((b) => { if (b !== exclusiveBox) b.checked = false; });
    } else if (changed.checked) {
      exclusiveBox.checked = false;
    }
    if (!boxes.some((b) => b.checked)) exclusiveBox.checked = true;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { exclusiveChoice };
  }
  if (typeof document === "undefined") return;

  document.querySelectorAll("[data-exclusive-choice]").forEach((group) => {
    const boxes = Array.from(group.querySelectorAll("input[type=checkbox]"));
    boxes.forEach((box) => {
      box.addEventListener("change", () => exclusiveChoice(boxes, box, group.dataset.exclusiveChoice));
    });
  });
})();
