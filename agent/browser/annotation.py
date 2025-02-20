from typing import Dict, List, Tuple

from playwright.async_api import Page

ANNOTATE_PAGE_TEMPLATE = r"""() => {
    const elements = Array.from(document.querySelectorAll("a, button, input, textarea, select"));
    let label_selectors = {};
    let label_simplified_htmls = {};

    function isHiddenByAncestors(element) {
        while (element) {
            const style = window.getComputedStyle(element);
            if (style.display === 'none' || style.visibility === 'hidden') {
                return true;
            }
            element = element.parentElement;
        }
        return false;
    }

    const getCssSelector = (element) => {
        if (element === null) return "";
        let path = [];
        while (element && element.nodeType === Node.ELEMENT_NODE) {
            let selector = element.nodeName.toLowerCase();
            if (element.id) {
                selector += "#" + element.id;
                path.unshift(selector);
                break;
            } else {
                let sib = element;
                let nth = 1;
                while ((sib = sib.previousElementSibling)) {
                    if (sib.nodeName.toLowerCase() == selector) nth++;
                }
                if (nth != 1) selector += ":nth-of-type(" + nth + ")";
            }
            path.unshift(selector);
            element = element.parentNode;
        }
        return path.join(" > ");
    };

    function isElementVisible(element) {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        
        // Basic size and style checks
        if (element.offsetWidth <= 1 || element.offsetHeight <= 1 ||
            style.visibility === 'hidden' || style.display === 'none' ||
            parseFloat(style.opacity) === 0) {
            return false;
        }

        // Check if element or its ancestors are hidden
        if (isHiddenByAncestors(element)) {
            return false;
        }

        // Check if element is actually clickable/interactive
        if (style.pointerEvents === 'none') {
            return false;
        }

        // Check if element is covered by other elements
        const elementAtPoint = document.elementFromPoint(
            rect.left + rect.width/2,
            rect.top + rect.height/2
        );
        if (!elementAtPoint || !element.contains(elementAtPoint)) {
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
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    }

    let visibleIndex = 0;
    elements.forEach((element) => {
        if (isElementVisible(element)) {
            const tagName = element.tagName.toLowerCase();
            let simplified_html = '<' + tagName;
            for (const attr of ['aria-label', 'alt', 'placeholder', 'value']) {
                if (element.hasAttribute(attr)) {
                    let attrValue = element.getAttribute(attr);
                    simplified_html += ` ${attr}="${attrValue}"`;
                }
            }

            // Get inner text from the element.
            let innerText = element.textContent.replace(/\n/g, ' ').trim();

            // For input elements, we need to look elsewhere for the visible label text.
            if (tagName === 'input' && innerText === '') {
                // 1. Try to get an associated label via the "for" attribute.
                if (element.id) {
                    const associatedLabel = document.querySelector(`label[for="${element.id}"]`);
                    if (associatedLabel) {
                        innerText = associatedLabel.textContent.replace(/\n/g, ' ').trim();
                    }
                }
                // 2. Check if the input is wrapped in a <label>.
                if (innerText === '' && element.parentElement && element.parentElement.tagName.toLowerCase() === 'label') {
                    innerText = element.parentElement.textContent.replace(/\n/g, ' ').trim();
                }
                // 3. Check if a sibling <span> element holds the text.
                if (innerText === '') {
                    if (element.nextElementSibling && element.nextElementSibling.tagName.toLowerCase() === 'span') {
                        innerText = element.nextElementSibling.textContent.replace(/\n/g, ' ').trim();
                    } else if (element.previousElementSibling && element.previousElementSibling.tagName.toLowerCase() === 'span') {
                        innerText = element.previousElementSibling.textContent.replace(/\n/g, ' ').trim();
                    }
                }
                // 4. Fallback to the "value" or "placeholder" attribute.
                if (innerText === '') {
                    innerText = element.getAttribute('value') || element.getAttribute('placeholder') || '';
                }
            }

            simplified_html = simplified_html + '>' + innerText + '</' + tagName + '>';
            simplified_html = simplified_html.replace(/\s+/g, ' ').trim();

            const cssSelector = getCssSelector(element);
            label_selectors[visibleIndex] = cssSelector;
            label_simplified_htmls[visibleIndex] = simplified_html;

            // Adjust positions with scroll offset
            const adjustedTop = element.getBoundingClientRect().top + window.scrollY;
            const adjustedLeft = element.getBoundingClientRect().left + window.scrollX;

            const newElement = document.createElement('div');
            newElement.className = 'autopilot-generated-rect';
            newElement.style.border = '2px solid brown';
            newElement.style.position = 'absolute';
            newElement.style.top = `${adjustedTop}px`;
            newElement.style.left = `${adjustedLeft}px`;
            newElement.style.width = `${element.getBoundingClientRect().width}px`;
            newElement.style.height = `${element.getBoundingClientRect().height}px`;
            newElement.style.zIndex = 10000;
            newElement.style.pointerEvents = 'none';
            document.body.appendChild(newElement);

            const label = document.createElement("span");
            label.className = "autopilot-generated-label";
            label.textContent = visibleIndex;
            label.style.position = "absolute";
            label.style.lineHeight = "16px";
            label.style.padding = "1px";
            label.style.top = `${adjustedTop}px`;
            label.style.left = `${adjustedLeft}px`;
            label.style.color = "white";
            label.style.fontWeight = "bold";
            label.style.fontSize = "16px";
            label.style.backgroundColor = "brown";
            label.style.zIndex = 10000;
            document.body.appendChild(label);

            visibleIndex++;
        }
    });
    return [label_selectors, label_simplified_htmls];
}"""


CLEAR_PAGE_TEMPLATE = """() => {
    const removeElementsByClass = (className) => {
        const elements = Array.from(document.querySelectorAll(className));
        elements.forEach((element, index) => {
            element.remove();
        });
    };
    removeElementsByClass(".autopilot-generated-rect");
    removeElementsByClass(".autopilot-generated-label");
}"""


async def annotate_page(page: Page) -> Tuple[Dict[int, str], Dict[int, str]]:
    label_selectors, label_simplified_htmls = await page.evaluate(
        ANNOTATE_PAGE_TEMPLATE
    )
    return label_selectors, label_simplified_htmls


async def clear_annotations(page: Page):
    await page.evaluate(CLEAR_PAGE_TEMPLATE)


GROUP_ANNOTATE_PAGE_TEMPLATE = r"""() => {
    // Utility: Checks if an element is hidden by any of its ancestors.
    function isHiddenByAncestors(element) {
        while (element) {
            const style = window.getComputedStyle(element);
            if (style.display === 'none' || style.visibility === 'hidden') {
                return true;
            }
            element = element.parentElement;
        }
        return false;
    }

    // Utility: Generates a unique (but more detailed) CSS selector for an element.
    const getCssSelector = (element) => {
        if (element === null) return "";
        let path = [];
        while (element && element.nodeType === Node.ELEMENT_NODE) {
            let selector = element.nodeName.toLowerCase();
            if (element.id) {
                selector += "#" + element.id;
                path.unshift(selector);
                break;
            } else {
                let sib = element;
                let nth = 1;
                while ((sib = sib.previousElementSibling)) {
                    if (sib.nodeName.toLowerCase() === selector) nth++;
                }
                if (nth !== 1) selector += ":nth-of-type(" + nth + ")";
            }
            path.unshift(selector);
            element = element.parentNode;
        }
        return path.join(" > ");
    };

    // Utility: Determines whether an element is visible.
    function isElementVisible(element) {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        
        if (element.offsetWidth <= 1 || element.offsetHeight <= 1 ||
            style.visibility === 'hidden' || style.display === 'none' ||
            parseFloat(style.opacity) === 0) {
            return false;
        }
        if (isHiddenByAncestors(element)) {
            return false;
        }
        if (style.pointerEvents === 'none') {
            return false;
        }
        const elementAtPoint = document.elementFromPoint(
            rect.left + rect.width / 2,
            rect.top + rect.height / 2
        );
        if (!elementAtPoint || !element.contains(elementAtPoint)) {
            return false;
        }
        if (rect.width * rect.height === 0) {
            return false;
        }
        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    }

    // New grouping strategy: Use a simplified key based on tag name and class.
    function getGroupKey(element) {
        // If the element is inside a container with "data-function-group", use that container's tag and classes.
        const container = element.closest("[data-function-group]");
        if (container) {
            const classPart = container.className ? '.' + container.className.trim().replace(/\s+/g, '.') : "";
            return container.tagName.toLowerCase() + classPart;
        }
        // Otherwise, group by the immediate parent's simplified representation.
        if (element.parentElement) {
            const parent = element.parentElement;
            const classPart = parent.className ? '.' + parent.className.trim().replace(/\s+/g, '.') : "";
            return parent.tagName.toLowerCase() + classPart;
        }
        return "default";
    }

    // Retrieve all interactive elements.
    const interactiveElements = Array.from(document.querySelectorAll("a, button, input, textarea, select"));
    let groups = {};
    let elementCounter = 0;

    // Process each element.
    interactiveElements.forEach((element) => {
        if (isElementVisible(element)) {
            const currentCount = elementCounter;
            elementCounter++;

            // Create a simplified HTML representation.
            let simplified_html = "<" + element.tagName.toLowerCase();
            for (const attr of ['aria-label', 'alt', 'placeholder', 'value']) {
                if (element.hasAttribute(attr)) {
                    let attrValue = element.getAttribute(attr);
                    simplified_html += ` ${attr}="${attrValue}"`;
                }
            }
            const textContent = element.textContent.replace(/\n/g, ' ');
            simplified_html += ">" + textContent + "</" + element.tagName.toLowerCase() + ">";
            simplified_html = simplified_html.replace(/\s+/g, ' ').trim();

            // Draw a bounding box with a number label.
            const rect = element.getBoundingClientRect();
            const adjustedTop = rect.top + window.scrollY;
            const adjustedLeft = rect.left + window.scrollX;

            const box = document.createElement('div');
            box.className = 'autopilot-generated-rect';
            box.style.border = '2px solid brown';
            box.style.position = 'absolute';
            box.style.top = `${adjustedTop}px`;
            box.style.left = `${adjustedLeft}px`;
            box.style.width = `${rect.width}px`;
            box.style.height = `${rect.height}px`;
            box.style.zIndex = 10000;
            box.style.pointerEvents = 'none';
            document.body.appendChild(box);

            const label = document.createElement("span");
            label.className = "autopilot-generated-label";
            label.textContent = currentCount;
            label.style.position = "absolute";
            label.style.lineHeight = "16px";
            label.style.padding = "1px";
            label.style.top = `${adjustedTop}px`;
            label.style.left = `${adjustedLeft}px`;
            label.style.color = "white";
            label.style.fontWeight = "bold";
            label.style.fontSize = "16px";
            label.style.backgroundColor = "brown";
            label.style.zIndex = 10000;
            document.body.appendChild(label);

            // Determine the group key using the simplified strategy.
            const groupKey = getGroupKey(element);
            if (!groups[groupKey]) {
                groups[groupKey] = [];
            }
            groups[groupKey].push({
                elementNumber: currentCount,
                cssSelector: getCssSelector(element),
                simplifiedHtml: simplified_html
            });
        }
    });
    
    // Return a list of groups (each group is a list of element data objects).
    return Object.values(groups);
}"""


async def annotate_page_grouped(page: Page) -> List[List[dict]]:
    """
    Annotates the page by grouping interactive elements based
    on a simplified DOM hierarchy. For each visible interactive element,
    a bounding box with a numbered label is drawn on the page and the
    element's data (including elementNumber, cssSelector, and simplifiedHtml)
    is returned within its group.
    """
    groups = await page.evaluate(GROUP_ANNOTATE_PAGE_TEMPLATE)
    return groups
