"""
Annotation actions for labeling and identifying interactive elements on web pages.
"""

from typing import Dict, Tuple

from playwright.async_api import Page

# JavaScript template for annotating page elements
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
                selector += "#" + CSS.escape(element.id);
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
        
        // Check if element or its ancestors are hidden
        if (isHiddenByAncestors(element)) {
            return false;
        }
        
        // Check if element has zero dimensions
        if (rect.width === 0 || rect.height === 0) {
            return false;
        }
        
        // Check if element is outside viewport
        if (rect.bottom < 0 || rect.right < 0 || rect.top > window.innerHeight || rect.left > window.innerWidth) {
            return false;
        }
        
        // Check if element has opacity 0
        if (parseFloat(style.opacity) === 0) {
            return false;
        }
        
        return true;
    }

    function getElementText(element) {
        // For inputs, return their value or placeholder
        if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
            if (element.value) return element.value;
            if (element.placeholder) return element.placeholder;
            if (element.name) return element.name;
            return element.type || 'input';
        }
        
        // For selects, get the selected option text
        if (element.tagName === 'SELECT') {
            if (element.options && element.selectedIndex >= 0) {
                return element.options[element.selectedIndex].text;
            }
            return 'select';
        }
        
        // For buttons and links, get their text content
        let text = element.textContent.trim();
        if (text) return text;
        
        // If no text content, try to get aria-label or title
        if (element.getAttribute('aria-label')) return element.getAttribute('aria-label');
        if (element.getAttribute('title')) return element.getAttribute('title');
        if (element.getAttribute('alt')) return element.getAttribute('alt');
        
        // If still no text, try to get any image alt text
        const img = element.querySelector('img');
        if (img && img.getAttribute('alt')) return img.getAttribute('alt');
        
        // Last resort: return the element type
        return element.tagName.toLowerCase();
    }

    function getSimplifiedHTML(element) {
        let clone = element.cloneNode(true);
        
        // Remove all script and style elements
        const scripts = clone.querySelectorAll('script, style');
        scripts.forEach(script => script.remove());
        
        // Get the HTML content
        let html = clone.outerHTML;
        
        // Simplify the HTML by removing most attributes except key ones
        html = html.replace(/<([a-z][a-z0-9]*)\s(?:[^>]*\s)?([^>]*)>/gi, (match, tag, attrs) => {
            // Keep only important attributes
            const keepAttrs = ['id', 'class', 'href', 'src', 'alt', 'title', 'value', 'placeholder', 'type', 'name', 'aria-label'];
            let newAttrs = '';
            
            for (const attr of keepAttrs) {
                const regex = new RegExp(`${attr}=["']([^"']*)["']`, 'i');
                const match = attrs.match(regex);
                if (match) {
                    newAttrs += ` ${attr}="${match[1]}"`;
                }
            }
            
            return `<${tag}${newAttrs}>`;
        });
        
        // Limit the length of the HTML
        if (html.length > 500) {
            html = html.substring(0, 497) + '...';
        }
        
        return html;
    }

    let labelIndex = 1;
    elements.forEach(element => {
        if (isElementVisible(element)) {
            const text = getElementText(element);
            const selector = getCssSelector(element);
            const simplifiedHTML = getSimplifiedHTML(element);
            
            label_selectors[labelIndex] = selector;
            label_simplified_htmls[labelIndex] = {
                "text": text,
                "html": simplifiedHTML,
                "tag": element.tagName.toLowerCase(),
                "type": element.type || ''
            };
            
            labelIndex++;
        }
    });

    return [label_selectors, label_simplified_htmls];
}"""


async def annotate_page(page: Page) -> Tuple[Dict[int, str], Dict[int, str]]:
    """
    Annotate the page with labels for interactive elements.

    Args:
        page: The Playwright page

    Returns:
        A tuple containing (label_selectors, label_simplified_htmls)
    """
    return await page.evaluate(ANNOTATE_PAGE_TEMPLATE)


CLEAR_PAGE_TEMPLATE = """() => {
    const removeElementsByClass = (className) => {
        const elements = Array.from(document.querySelectorAll(className));
        elements.forEach((element, index) => {
            element.remove();
        });
    };
    removeElementsByClass(".GWA-rect");
    removeElementsByClass(".GWA-label");
}"""


async def clear_annotations(page: Page) -> None:
    """
    Clear any annotations from the page.

    Args:
        page: The Playwright page
    """
    await page.evaluate(CLEAR_PAGE_TEMPLATE)
