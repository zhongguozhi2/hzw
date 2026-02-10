const puppeteer = require('puppeteer');
const readline = require('readline');

(async () => {
    try {
        console.log("Launching Chrome...");
        const browser = await puppeteer.launch({
            headless: false,
            executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
            defaultViewport: null,
            args: ['--start-maximized']
        });

        const pages = await browser.pages();
        const page = pages.length > 0 ? pages[0] : await browser.newPage();

        console.log("Navigating to https://www.xnowpay.com ...");
        await page.goto('https://www.xnowpay.com', { waitUntil: 'networkidle2' });

        console.log("Page title:", await page.title());

        // Attempt to find and click Login button
        // Strategies:
        // 1. Link with text "Login" or "Log In"
        // 2. Button with text "Login"
        
        const loginSelectors = [
            "//a[contains(translate(., 'LOGIN', 'login'), 'login')]",
            "//button[contains(translate(., 'LOGIN', 'login'), 'login')]",
            "//span[contains(translate(., 'LOGIN', 'login'), 'login')]"
        ];

        let loginClicked = false;
        for (const selector of loginSelectors) {
            try {
                const elements = await page.$x(selector);
                for (const el of elements) {
                    if (await el.isIntersectingViewport()) {
                        console.log("Found visible login element, clicking...");
                        await el.click();
                        loginClicked = true;
                        break;
                    }
                }
                if (loginClicked) break;
            } catch (e) {
                // ignore
            }
        }
        
        if (!loginClicked) {
            console.log("Could not click a 'Login' link/button specifically. Checking if we are already on a login page or if form is visible.");
        }

        // Wait for inputs
        // Email
        const emailSelectors = ["input[name='email']", "input[name='username']", "input[type='email']", "input[placeholder*='Email']"];
        let emailInput = null;
        for (const sel of emailSelectors) {
            try {
                await page.waitForSelector(sel, { timeout: 3000, visible: true });
                emailInput = sel;
                console.log(`Found email input: ${sel}`);
                break;
            } catch (e) {}
        }

        if (emailInput) {
            await page.type(emailInput, "bala@gmail.com", { delay: 50 });
        } else {
            console.log("Could not find email input field.");
        }

        // Password
        const passwordSelectors = ["input[name='password']", "input[type='password']", "input[placeholder*='Password']"];
        let passwordInput = null;
        for (const sel of passwordSelectors) {
            try {
                await page.waitForSelector(sel, { timeout: 3000, visible: true });
                passwordInput = sel;
                console.log(`Found password input: ${sel}`);
                break;
            } catch (e) {}
        }

        if (passwordInput) {
            await page.type(passwordInput, "Xnowpay123456.", { delay: 50 });
        } else {
            console.log("Could not find password input field.");
        }

        // Submit
        if (emailInput && passwordInput) {
            console.log("Submitting form...");
            const submitSelectors = ["button[type='submit']", "input[type='submit']", "//button[contains(., 'Login')]", "//button[contains(., 'Sign In')]"];
            let submitted = false;
            
            // Try standard submit button first
            try {
                await page.click("button[type='submit']");
                submitted = true;
            } catch(e) {}
            
            if (!submitted) {
                 await page.keyboard.press('Enter');
            }
            
            console.log("Form submitted (or attempted).");
        }
        
        console.log("Task completed. Browser is open.");
        console.log("Press Enter in this terminal to close the browser...");
        
        const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout
        });
        
        rl.question('', (answer) => {
            console.log("Closing browser...");
            browser.close();
            rl.close();
        });

    } catch (error) {
        console.error("An error occurred:", error);
    }
})();
