() => {
  // Remove any existing data-gwa-id attributes to avoid duplicates
  document.querySelectorAll("[data-gwa-id]").forEach((el) => {
    el.removeAttribute("data-gwa-id");
  });
  document.querySelectorAll("[data-bbox-gwa-id]").forEach((el) => {
    el.removeAttribute("data-bbox-gwa-id");
  });

  const elements = Array.from(
    document.querySelectorAll(
      "a, button, input, textarea, select, [role='button'], [role='combobox'], [role='listbox'], [role='menuitem'], [role='tab'], [role='link']"
    )
  );
  let element_simplified_htmls = {}; // HTML for each element index

  function isHiddenByAncestors(element) {
    while (element) {
      const style = window.getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden") {
        return true;
      }
      element = element.parentElement;
    }
    return false;
  }

  function getParentWithLabel(element) {
    // If input has an associated label via 'for' attribute
    if (element.id) {
      const associatedLabel = document.querySelector(
        `label[for="${element.id}"]`
      );
      if (associatedLabel) {
        // Find common parent of input and label
        let inputParent = element.parentElement;
        while (inputParent) {
          if (inputParent.contains(associatedLabel)) {
            return inputParent;
          }
          inputParent = inputParent.parentElement;
        }
      }
    }

    // If input is wrapped in a label
    let parent = element.parentElement;
    while (parent) {
      if (parent.tagName.toLowerCase() === "label") {
        return parent;
      }
      // Check if parent contains a label for this input
      const childLabels = parent.getElementsByTagName("label");
      for (const label of childLabels) {
        if (
          label.getAttribute("for") === element.id ||
          label.contains(element)
        ) {
          return parent;
        }
      }
      parent = parent.parentElement;
    }

    return element; // fallback to the element itself
  }

  function isElementVisible(element) {
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);

    // Check if element or its ancestors are hidden
    if (isHiddenByAncestors(element)) {
      return false;
    }

    // Check if element is actually clickable/interactive
    if (style.pointerEvents === "none") {
      return false;
    }

    // Special handling for small form elements
    const isHTMLInputElement = element.tagName.toLowerCase() === "input";
    const inputElement = element;
    const htmlElement = element;
    const isSmallFormElement =
      isHTMLInputElement &&
      (inputElement.type === "radio" || inputElement.type === "checkbox") &&
      htmlElement.offsetWidth <= 1 &&
      htmlElement.offsetHeight <= 1;

    // Basic size and style checks (skip for small form elements)
    if (
      !isSmallFormElement &&
      (htmlElement.offsetWidth <= 1 ||
        htmlElement.offsetHeight <= 1 ||
        style.visibility === "hidden" ||
        style.display === "none")
    ) {
      return false;
    }

    // For small form elements, check parent element dimensions
    if (isSmallFormElement) {
      const parentWithLabel = getParentWithLabel(element);
      if (parentWithLabel !== element) {
        const parentRect = parentWithLabel.getBoundingClientRect();
        if (parentRect.width <= 1 || parentRect.height <= 1) {
          return false;
        }
      }
    }

    // Check if element is covered by other elements
    const elementAtPoint = document.elementFromPoint(
      rect.left + rect.width / 2,
      rect.top + rect.height / 2
    );

    // For form elements, check if clicking their label or container would trigger them
    if (
      isHTMLInputElement &&
      (inputElement.type === "radio" || inputElement.type === "checkbox")
    ) {
      // Consider the element visible if we hit its label or a parent with click handler
      let currentElement = elementAtPoint;
      while (currentElement) {
        if (
          currentElement.tagName.toLowerCase() === "label" &&
          currentElement.getAttribute("for") === element.id
        ) {
          return true;
        }
        // Check if this is an ancestor that would handle the click
        if (currentElement.contains(element)) {
          return true;
        }
        currentElement = currentElement.parentElement;
      }
    }

    // General visibility check for other elements
    if (
      !elementAtPoint ||
      (elementAtPoint !== element &&
        !element.contains(elementAtPoint) &&
        !elementAtPoint.contains(element))
    ) {
      return false;
    }

    // Check if element has meaningful dimensions
    if (rect.width * rect.height === 0) {
      return false;
    }

    // Viewport visibility check
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <=
        (window.innerHeight || document.documentElement.clientHeight) &&
      rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
  }

  let visibleIndex = 0;
  elements.forEach((element) => {
    if (isElementVisible(element)) {
      const tagName = element.tagName.toLowerCase();
      let simplified_html = "<" + tagName;
      for (const attr of ["aria-label", "alt", "placeholder", "value"]) {
        if (element.hasAttribute(attr)) {
          let attrValue = element.getAttribute(attr);
          simplified_html += ` ${attr}="${attrValue}"`;
        }
      }

      // Get inner text from the element.
      let innerText = element.textContent?.replace(/\n/g, " ").trim() || "";

      // For input elements, we need to look elsewhere for the visible label text.
      if (tagName === "input" && innerText === "") {
        // 1. Try to get an associated label via the "for" attribute.
        if (element.id) {
          const associatedLabel = document.querySelector(
            `label[for="${element.id}"]`
          );
          if (associatedLabel) {
            innerText =
              associatedLabel.textContent?.replace(/\n/g, " ").trim() || "";
          }
        }
        // 2. Check if the input is wrapped in a <label>.
        if (
          innerText === "" &&
          element.parentElement &&
          element.parentElement.tagName.toLowerCase() === "label"
        ) {
          innerText =
            element.parentElement.textContent?.replace(/\n/g, " ").trim() || "";
        }
        // 3. Check if a sibling <span> element holds the text.
        if (innerText === "") {
          if (
            element.nextElementSibling &&
            element.nextElementSibling.tagName.toLowerCase() === "span"
          ) {
            innerText =
              element.nextElementSibling.textContent
                ?.replace(/\n/g, " ")
                .trim() || "";
          } else if (
            element.previousElementSibling &&
            element.previousElementSibling.tagName.toLowerCase() === "span"
          ) {
            innerText =
              element.previousElementSibling.textContent
                ?.replace(/\n/g, " ")
                .trim() || "";
          }
        }
        // 4. Fallback to the "value" or "placeholder" attribute.
        if (innerText === "") {
          innerText =
            element.getAttribute("value") ||
            element.getAttribute("placeholder") ||
            "";
        }
      }

      simplified_html =
        simplified_html + ">" + innerText + "</" + tagName + ">";
      simplified_html = simplified_html.replace(/\s+/g, " ").trim();

      element.setAttribute("data-gwa-id", `gwa-element-${visibleIndex}`);

      // For these elements, use the parent element that contains the label for the bounding box
      if (
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select"
      ) {
        const bboxElement = getParentWithLabel(element);
        bboxElement.setAttribute(
          "data-bbox-gwa-id",
          `gwa-element-${visibleIndex}`
        );
      } else {
        element.setAttribute("data-bbox-gwa-id", `gwa-element-${visibleIndex}`);
      }

      // Set a data attribute to uniquely identify the element using the visible index

      // Store simplified HTML with visible index as key
      element_simplified_htmls[visibleIndex] = simplified_html;

      visibleIndex++;
    }
  });
  return element_simplified_htmls;
};
