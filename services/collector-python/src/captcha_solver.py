"""
CAPTCHA detection and solving using 2Captcha API with OCR fallback.
"""

import base64
import logging
from io import BytesIO
from typing import Optional

from playwright.async_api import Page
from twocaptcha import TwoCaptcha
import pytesseract
from PIL import Image


class CaptchaSolver:
    """Solves reCAPTCHA, hCaptcha, and image-based CAPTCHAs."""
    
    def __init__(self, api_key: str, logger: logging.Logger):
        self.logger = logger
        self.api_key = api_key
        self.solver = TwoCaptcha(api_key) if api_key else None
    
    async def solve(self, page: Page) -> bool:
        """
        Detect and solve CAPTCHA on the page.
        Returns True if CAPTCHA was solved, False otherwise.
        """
        
        # Try reCAPTCHA v2
        if await self._try_solve_recaptcha_v2(page):
            return True
        
        # Try hCaptcha
        if await self._try_solve_hcaptcha(page):
            return True
        
        # Try image-based CAPTCHA with OCR
        if await self._try_solve_image_captcha(page):
            return True
        
        return False
    
    async def _try_solve_recaptcha_v2(self, page: Page) -> bool:
        """Solve reCAPTCHA v2."""
        if not self.solver:
            return False
        
        try:
            iframe = await page.query_selector('iframe[src*="recaptcha"]')
            if not iframe:
                return False
            
            site_key = await page.evaluate(
                "() => window.grecaptcha ? window.grecaptcha.getResponse() : null"
            )
            
            if not site_key:
                # Extract sitekey from page source
                content = await page.content()
                import re
                match = re.search(r'data-sitekey="([^"]+)"', content)
                if not match:
                    return False
                site_key = match.group(1)
            
            # Call 2Captcha API
            result = self.solver.recaptcha(sitekey=site_key, pageurl=page.url)
            
            # Inject solution
            await page.evaluate(
                f"window.grecaptcha.callback('{result['code']}')",
                timeout=5000
            )
            
            self.logger.info('"Solved reCAPTCHA v2"')
            return True
        
        except Exception as e:
            self.logger.warning('"reCAPTCHA v2 solve failed: %s"', e)
            return False
    
    async def _try_solve_hcaptcha(self, page: Page) -> bool:
        """Solve hCaptcha."""
        if not self.solver:
            return False
        
        try:
            iframe = await page.query_selector('iframe[src*="hcaptcha"]')
            if not iframe:
                return False
            
            # Extract sitekey
            content = await page.content()
            import re
            match = re.search(r'data-sitekey="([^"]+)"', content)
            if not match:
                return False
            
            site_key = match.group(1)
            
            # Call 2Captcha for hCaptcha
            result = self.solver.hcaptcha(sitekey=site_key, pageurl=page.url)
            
            # Inject solution
            await page.evaluate(
                f"window.hcaptcha.getResponse = () => '{result['code']}'; "
                f"document.querySelector('[data-sitekey]').parentElement.querySelector('button').click();"
            )
            
            self.logger.info('"Solved hCaptcha"')
            return True
        
        except Exception as e:
            self.logger.warning('"hCaptcha solve failed: %s"', e)
            return False
    
    async def _try_solve_image_captcha(self, page: Page) -> bool:
        """Solve image-based CAPTCHA using Tesseract OCR."""
        try:
            # Find CAPTCHA image
            img_selectors = [
                'img[alt*="captcha" i]',
                'img[id*="captcha" i]',
                'img.captcha',
            ]
            
            img_element = None
            for selector in img_selectors:
                img_element = await page.query_selector(selector)
                if img_element:
                    break
            
            if not img_element:
                return False
            
            # Extract image
            screenshot = await img_element.screenshot()
            image = Image.open(BytesIO(screenshot))
            
            # Preprocess image (enhance contrast)
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2)
            
            # OCR
            text = pytesseract.image_to_string(image).strip()
            
            if not text or len(text) < 2:
                self.logger.warning('"OCR failed to extract CAPTCHA text"')
                return False
            
            # Find input field and submit
            input_selectors = [
                'input[name*="captcha"]',
                'input[type="text"]:near(img[alt*="captcha" i])',
            ]
            
            for selector in input_selectors:
                input_field = await page.query_selector(selector)
                if input_field:
                    await input_field.fill(text)
                    break
            
            # Submit form
            form = await img_element.evaluate_handle("el => el.closest('form')")
            if form:
                await page.evaluate_handle("form => form.submit()", form)
                await page.wait_for_navigation(timeout=5000)
            
            self.logger.info('"Solved image CAPTCHA with OCR: %s"', text)
            return True
        
        except Exception as e:
            self.logger.debug('"Image CAPTCHA solve failed: %s"', e)
            return False
