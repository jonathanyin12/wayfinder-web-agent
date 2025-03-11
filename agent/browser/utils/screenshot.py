"""
Screenshot actions for capturing the page or specific elements.
"""

import base64
from pathlib import Path
from typing import Optional

from playwright.async_api import Page


async def take_screenshot(
    page: Page, save_path: Optional[str] = None, full_page: bool = False
) -> str:
    """
    Take a screenshot of the current page.

    Args:
        page: The Playwright page
        save_path: Path to save the screenshot
        full_page: Whether to capture the full page or just the viewport

    Returns:
        Base64-encoded string of the screenshot
    """
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    screenshot = await page.screenshot(full_page=full_page, path=save_path)
    return base64.b64encode(screenshot).decode("utf-8")


async def take_element_screenshot(
    page: Page, selector: str, save_path: Optional[str] = None
) -> Optional[str]:
    """
    Take a screenshot of a specific element on the page.

    Args:
        page: The Playwright page
        selector: CSS selector for the element to capture
        save_path: Path to save the screenshot

    Returns:
        Base64-encoded string of the screenshot, or None if element not found
    """
    # First try to find the element directly
    element = await page.query_selector(selector)

    if not element:
        return None

    # For radio/checkbox inputs, we may want to capture parent with label
    is_special_input = await element.evaluate("""
        element => element.tagName.toLowerCase() === 'input' && 
                  (element.type === 'radio' || element.type === 'checkbox')
    """)

    if is_special_input:
        # Find the target element using the original algorithm
        target_selector = await page.evaluate(
            """(selector) => {
            const element = document.querySelector(selector);
            
            // Find parent with label
            function getParentWithLabel(element) {
                // If input has an associated label via 'for' attribute
                if (element.id) {
                    const associatedLabel = document.querySelector(`label[for="${element.id}"]`);
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
                    if (parent.tagName.toLowerCase() === 'label') {
                        return parent;
                    }
                    // Check if parent contains a label for this input
                    const childLabels = parent.getElementsByTagName('label');
                    for (const label of childLabels) {
                        if (label.getAttribute('for') === element.id || label.contains(element)) {
                            return parent;
                        }
                    }
                    parent = parent.parentElement;
                }
                
                return element; // fallback to the element itself
            }
            
            const target = getParentWithLabel(element);
            
            // Generate a more reliable CSS selector for the target
            function generateSelector(el) {
                if (el === document.body) return 'body';
                if (!el) return null;
                
                // If element has an ID, that's the most specific selector
                if (el.id) return `#${CSS.escape(el.id)}`;
                
                // Try to create a specific path using nth-child
                let path = [];
                while (el && el.nodeType === Node.ELEMENT_NODE) {
                    let selector = el.nodeName.toLowerCase();
                    
                    if (el.id) {
                        selector += `#${CSS.escape(el.id)}`;
                        path.unshift(selector);
                        break;
                    } else {
                        let siblings = Array.from(el.parentNode.children).filter(
                            child => child.nodeName === el.nodeName
                        );
                        
                        if (siblings.length > 1) {
                            let index = siblings.indexOf(el) + 1;
                            selector += `:nth-child(${index})`;
                        }
                        
                        path.unshift(selector);
                        el = el.parentNode;
                    }
                }
                
                return path.join(' > ');
            }
            
            const targetSelector = generateSelector(target);
            return targetSelector || selector; // fallback to original selector if generation fails
        }""",
            selector,
        )

        # Use the identified target selector
        if target_selector and target_selector != selector:
            element = await page.query_selector(target_selector)
            if not element:
                element = await page.query_selector(selector)  # Fallback

    if element:
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        screenshot = await element.screenshot(path=save_path)
        return base64.b64encode(screenshot).decode("utf-8")
    return None
