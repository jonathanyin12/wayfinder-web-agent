(indices) => {
  // If no indices provided, draw boxes for all elements with data-gwa-id
  if (!indices || indices.length === 0) {
    indices = Array.from(document.querySelectorAll("[data-gwa-id]")).map(
      (el) => {
        const id = el.getAttribute("data-gwa-id");
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
      `[data-gwa-id="gwa-element-${index}"]`
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
    newElement.style.zIndex = "10000";
    newElement.style.pointerEvents = "none";
    document.body.appendChild(newElement);

    // Create label with index number
    const label = document.createElement("span");
    label.className = "GWA-label";
    label.textContent = index;
    label.style.position = "absolute";
    label.style.lineHeight = "16px";
    label.style.padding = "1px";
    label.style.top = `${adjustedTop}px`;
    label.style.left = `${adjustedLeft}px`;
    label.style.color = "white";
    label.style.fontWeight = "bold";
    label.style.fontSize = "16px";
    label.style.backgroundColor = "brown";
    label.style.zIndex = "10000";
    document.body.appendChild(label);
  });

  return indices.length;
};
