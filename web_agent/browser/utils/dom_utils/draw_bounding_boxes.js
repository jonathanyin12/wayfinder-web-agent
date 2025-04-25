(indices) => {
  // If no indices provided, draw boxes for all elements with data-gwa-id
  if (!indices || indices.length === 0) {
    indices = Array.from(document.querySelectorAll("[data-gwa-id]")).map(
      (el) => {
        const id = el.getAttribute("data-bbox-gwa-id");
        return parseInt(id?.replace("gwa-element-", "") || "0");
      }
    );
  }

  // Clear any existing annotations first
  const removeElementsByClass = (className) => {
    const elements = Array.from(document.querySelectorAll(className));
    elements.forEach((element) => {
      element.remove();
    });
  };
  removeElementsByClass(".GWA-rect");
  removeElementsByClass(".GWA-label");

  // Draw new annotations
  indices.forEach((index) => {
    const element = document.querySelector(
      `[data-bbox-gwa-id="gwa-element-${index}"]`
    );
    if (!element) return;

    const rect = element.getBoundingClientRect();
    const adjustedTop = rect.top + window.scrollY;
    const adjustedLeft = rect.left + window.scrollX;

    // Create rectangle around element
    const newElement = document.createElement("div");
    newElement.className = "GWA-rect";
    newElement.style.border = "2px solid brown";
    newElement.style.position = "absolute";
    newElement.style.top = `${adjustedTop}px`;
    newElement.style.left = `${adjustedLeft}px`;
    newElement.style.width = `${rect.width}px`;
    newElement.style.height = `${rect.height}px`;
    newElement.style.zIndex = "2147483647";
    newElement.style.pointerEvents = "none";
    newElement.style.backgroundColor = "rgba(165, 42, 42, 0.1)";
    document.body.appendChild(newElement);

    // Create label with index number
    const label = document.createElement("span");
    label.className = "GWA-label";
    label.textContent = index;
    label.style.position = "absolute";
    label.style.lineHeight = "16px";
    label.style.padding = "1px";
    label.style.color = "white";
    label.style.fontWeight = "bold";
    label.style.fontSize = "14px";
    label.style.backgroundColor = "brown";
    label.style.zIndex = "2147483647";

    // Adjust label position if the element is too small vertically
    if (rect.height < 24 || rect.width < 24) {
      label.style.top = `${adjustedTop - 16}px`;
      label.style.left = `${adjustedLeft}px`;
    } else {
      label.style.top = `${adjustedTop}px`;
      label.style.left = `${adjustedLeft}px`;
    }

    document.body.appendChild(label);
  });

  return indices.length;
};
