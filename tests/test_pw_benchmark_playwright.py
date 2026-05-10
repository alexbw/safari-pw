"""Benchmark: pw (Safari JXA) vs Playwright (Chromium) on the same 6 sites.

Runs each site flow using Playwright's Python API directly, timing each step.
Compare results against the pw Safari tests.

Run: pytest tests/test_pw_benchmark_playwright.py -v -s
"""

import json
import os
import sys
import time

import pytest

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


pytestmark = pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright not installed")


def timed(name, timings):
    """Context manager to time a step."""
    class Timer:
        def __init__(self):
            self.t0 = None
        def __enter__(self):
            self.t0 = time.time()
            return self
        def __exit__(self, *args):
            timings[name] = time.time() - self.t0
    return Timer()


@pytest.fixture(scope="module")
def browser_context():
    """Launch Chromium once for all tests in this module."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    yield context
    context.close()
    browser.close()
    pw.stop()


class TestHertzPlaywright:
    def test_hertz_booking_flow(self, browser_context):
        timings = {}
        page = browser_context.new_page()

        with timed("1_navigate", timings):
            page.goto("https://www.hertz.com/us/en", wait_until="domcontentloaded", timeout=45000)

        with timed("2_location", timings):
            page.wait_for_selector("#locationInput", timeout=10000)
            page.fill("#locationInput", "EWR")
            time.sleep(2)
            try:
                page.click("#locationInput-option-0", timeout=5000)
            except Exception:
                # Retry
                page.fill("#locationInput", "")
                page.fill("#locationInput", "EWR")
                time.sleep(3)
                page.click("#locationInput-option-0", timeout=5000)

        with timed("3_date_picker", timings):
            # Try clicking date trigger — may be blocked by overlay
            trigger = "#dateTimePickerTriggerFrom"
            if not page.query_selector(trigger):
                trigger = "#dateTimePickerMobileTrigger"
            try:
                page.click(trigger, timeout=5000)
            except Exception:
                # Overlay blocks — use JS click
                page.evaluate(f"document.querySelector('{trigger}')?.click()")
            time.sleep(1)

        with timed("4_dates", timings):
            # Select dates via JS (overlay blocks Playwright clicks on calendar)
            page.evaluate("var el=document.querySelector(\"[aria-label='Fri Apr 03 2026']\"); if(el) el.click()")
            time.sleep(0.5)
            page.evaluate("var el=document.querySelector(\"[aria-label='Sun Apr 12 2026']\"); if(el) el.click()")
            time.sleep(0.5)

        with timed("5_time", timings):
            # Set time via React fiber
            page.evaluate("""(function(){
                var el = document.getElementById('dateTimePicker-timePicker-from');
                if(!el) return;
                var k = Object.keys(el).find(x => x.startsWith('__reactFiber'));
                if(!k) return;
                var fiber = el[k], cur = fiber;
                while(cur) {
                    if(cur.memoizedProps && cur.memoizedProps.onChange) {
                        cur.memoizedProps.onChange({target:{value:'10:00'}});
                        break;
                    }
                    cur = cur.return;
                }
            })()""")

        with timed("6_view_vehicles", timings):
            # Apply
            page.evaluate("""(function(){
                var btns = document.querySelectorAll('button');
                for(var i=0;i<btns.length;i++){
                    if(btns[i].textContent.trim()==='Apply'){btns[i].click();break}
                }
            })()""")
            time.sleep(1)
            # View vehicles
            try:
                page.click("text=View vehicles", timeout=5000)
            except Exception:
                page.evaluate("document.querySelector('form')?.submit()")
            time.sleep(6)
            # Wait for vehicles
            for _ in range(5):
                cards = page.evaluate("document.querySelectorAll('[id$=vehicle_pricing]').length")
                if cards > 0:
                    break
                time.sleep(3)

        with timed("7_select_vehicle", timings):
            first_id = page.evaluate(
                "(function(){var c=document.querySelectorAll('[id$=vehicle_pricing]');"
                "return c.length>0?c[0].id:'none'})()"
            )
            if first_id != "none":
                page.evaluate(f"document.getElementById('{first_id}')?.click()")
                time.sleep(4)

        with timed("8_skip_coverage", timings):
            page.evaluate("""(function(){
                var cb = document.querySelector('#no-coverage-checkbox');
                if(cb) cb.click();
            })()""")
            time.sleep(0.5)
            page.evaluate("""(function(){
                history.pushState(null,'','/us/en/book/ancillaries/extras'+window.location.search);
                window.dispatchEvent(new PopStateEvent('popstate'));
            })()""")
            time.sleep(3)

        with timed("9_skip_extras", timings):
            try:
                page.click("text=Continue", timeout=5000)
            except Exception:
                page.evaluate("""(function(){
                    history.pushState(null,'','/us/en/book/checkout'+window.location.search);
                    window.dispatchEvent(new PopStateEvent('popstate'));
                })()""")
            time.sleep(3)

        timings["total"] = sum(timings.values())
        path = page.evaluate("window.location.pathname")
        page.close()

        print("\n" + "=" * 60)
        print("HERTZ — PLAYWRIGHT (Chromium headless)")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  Final path: {path}")
        print("=" * 60)


class TestNJTransitPlaywright:
    def test_njtransit_form(self, browser_context):
        timings = {}
        page = browser_context.new_page()

        with timed("1_navigate", timings):
            page.goto("https://njtransit.my.salesforce-sites.com/customerservice/site_app#/contactus",
                      wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)

        with timed("2_fill_form", timings):
            page.evaluate("""(function(){
                var type = document.querySelector('select[name="input.Type"]');
                if(type){type.value='Complaint';type.dispatchEvent(new Event('change',{bubbles:true}))}
                var mode = document.querySelector('select[name="input.Mode__c"]');
                if(mode){mode.value='Rail';mode.dispatchEvent(new Event('change',{bubbles:true}))}
            })()""")
            time.sleep(1)
            page.evaluate("""(function(){
                var subj = document.querySelector('input[name="input.Subject"]');
                if(subj){subj.value='Playwright test';subj.dispatchEvent(new Event('input',{bubbles:true}))}
                var fn = document.querySelector('input[name="input.Customer_First_Name__c"]');
                if(fn){fn.value='Test';fn.dispatchEvent(new Event('input',{bubbles:true}))}
                var ln = document.querySelector('input[name="input.Customer_Last_Name__c"]');
                if(ln){ln.value='User';ln.dispatchEvent(new Event('input',{bubbles:true}))}
                var em = document.querySelector('input[name="input.SuppliedEmail"]');
                if(em){em.value='test@example.com';em.dispatchEvent(new Event('input',{bubbles:true}))}
                var em2 = document.querySelector('input[name="input.verifiedEmail"]');
                if(em2){em2.value='test@example.com';em2.dispatchEvent(new Event('input',{bubbles:true}))}
            })()""")

        timings["total"] = sum(timings.values())
        page.close()

        print("\n" + "=" * 60)
        print("NJ TRANSIT — PLAYWRIGHT (Chromium headless)")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print("=" * 60)


class TestOpenTablePlaywright:
    def test_opentable_search(self, browser_context):
        timings = {}
        page = browser_context.new_page()

        with timed("1_navigate", timings):
            page.goto("https://www.opentable.com", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

        with timed("2_search", timings):
            page.evaluate("""(function(){
                var inputs = document.querySelectorAll('input');
                for(var i=0;i<inputs.length;i++){
                    var ph = (inputs[i].placeholder||'').toLowerCase();
                    if(ph.indexOf('location')>-1||ph.indexOf('restaurant')>-1){
                        var ns=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
                        ns.call(inputs[i],'Manhattan');
                        inputs[i].dispatchEvent(new Event('input',{bubbles:true}));
                        break;
                    }
                }
            })()""")
            time.sleep(2)

        with timed("3_click_search", timings):
            page.evaluate("""(function(){
                var btns=document.querySelectorAll('button,a,[role=button]');
                for(var i=0;i<btns.length;i++){
                    var t=btns[i].textContent.trim().toLowerCase();
                    if(t==='find a table'||t==='search'||t.indexOf('find')>-1&&t.length<30){
                        btns[i].click();break;
                    }
                }
            })()""")
            time.sleep(5)

        timings["total"] = sum(timings.values())
        url = page.evaluate("window.location.href")
        page.close()

        print("\n" + "=" * 60)
        print("OPENTABLE — PLAYWRIGHT (Chromium headless)")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  URL: {url[:80]}")
        print("=" * 60)


class TestUnitedPlaywright:
    def test_united_flight_search(self, browser_context):
        timings = {}
        page = browser_context.new_page()

        with timed("1_navigate", timings):
            page.goto("https://www.united.com/en/us", wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)

        with timed("2_origin", timings):
            page.evaluate("""(function(){
                var inputs=document.querySelectorAll('input');
                for(var i=0;i<inputs.length;i++){
                    var ph=(inputs[i].placeholder||'').toLowerCase();
                    var label=(inputs[i].getAttribute('aria-label')||'').toLowerCase();
                    if(ph.indexOf('from')>-1||label.indexOf('from')>-1){
                        inputs[i].focus();inputs[i].value='EWR';
                        inputs[i].dispatchEvent(new Event('input',{bubbles:true}));break;
                    }
                }
            })()""")
            time.sleep(2)
            page.evaluate("""(function(){
                var opts=document.querySelectorAll('[role=option],li[class*=suggestion]');
                if(opts.length>0)opts[0].click();
            })()""")

        with timed("3_destination", timings):
            page.evaluate("""(function(){
                var inputs=document.querySelectorAll('input');
                for(var i=0;i<inputs.length;i++){
                    var ph=(inputs[i].placeholder||'').toLowerCase();
                    var label=(inputs[i].getAttribute('aria-label')||'').toLowerCase();
                    if(ph.indexOf('to')>-1||label.indexOf('to')>-1){
                        inputs[i].focus();inputs[i].value='SFO';
                        inputs[i].dispatchEvent(new Event('input',{bubbles:true}));break;
                    }
                }
            })()""")
            time.sleep(2)
            page.evaluate("""(function(){
                var opts=document.querySelectorAll('[role=option],li[class*=suggestion]');
                if(opts.length>0)opts[0].click();
            })()""")

        with timed("4_search", timings):
            page.evaluate("""(function(){
                var btns=document.querySelectorAll('button');
                for(var i=0;i<btns.length;i++){
                    var t=btns[i].textContent.trim().toLowerCase();
                    if(t.indexOf('search')>-1||t.indexOf('find flight')>-1){
                        btns[i].click();break;
                    }
                }
            })()""")
            time.sleep(8)

        timings["total"] = sum(timings.values())
        url = page.evaluate("window.location.href")
        page.close()

        print("\n" + "=" * 60)
        print("UNITED — PLAYWRIGHT (Chromium headless)")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  URL: {url[:80]}")
        print("=" * 60)


class TestAmtrakPlaywright:
    def test_amtrak_train_search(self, browser_context):
        timings = {}
        page = browser_context.new_page()

        with timed("1_navigate", timings):
            page.goto("https://www.amtrak.com", wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)

        with timed("2_origin", timings):
            page.evaluate("""(function(){
                var inputs=document.querySelectorAll('input');
                for(var i=0;i<inputs.length;i++){
                    var ph=(inputs[i].placeholder||'').toLowerCase();
                    var label=(inputs[i].getAttribute('aria-label')||'').toLowerCase();
                    if(ph.indexOf('from')>-1||label.indexOf('from')>-1||ph.indexOf('depart')>-1){
                        inputs[i].focus();inputs[i].value='New York Penn';
                        inputs[i].dispatchEvent(new Event('input',{bubbles:true}));break;
                    }
                }
            })()""")
            time.sleep(2)
            page.evaluate("var o=document.querySelectorAll('[role=option],mat-option');if(o.length>0)o[0].click()")

        with timed("3_destination", timings):
            page.evaluate("""(function(){
                var inputs=document.querySelectorAll('input');
                for(var i=0;i<inputs.length;i++){
                    var ph=(inputs[i].placeholder||'').toLowerCase();
                    var label=(inputs[i].getAttribute('aria-label')||'').toLowerCase();
                    if(ph.indexOf('to')>-1||label.indexOf('to')>-1||label.indexOf('arriv')>-1){
                        inputs[i].focus();inputs[i].value='Newark';
                        inputs[i].dispatchEvent(new Event('input',{bubbles:true}));break;
                    }
                }
            })()""")
            time.sleep(2)
            page.evaluate("var o=document.querySelectorAll('[role=option],mat-option');if(o.length>0)o[0].click()")

        with timed("4_search", timings):
            page.evaluate("""(function(){
                var btns=document.querySelectorAll('button');
                for(var i=0;i<btns.length;i++){
                    var t=btns[i].textContent.trim().toLowerCase();
                    if(t.indexOf('find train')>-1||t==='search trains'||t.indexOf('search')>-1){
                        btns[i].click();break;
                    }
                }
            })()""")
            time.sleep(8)

        timings["total"] = sum(timings.values())
        url = page.evaluate("window.location.href")
        page.close()

        print("\n" + "=" * 60)
        print("AMTRAK — PLAYWRIGHT (Chromium headless)")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  URL: {url[:80]}")
        print("=" * 60)


class TestExpediaPlaywright:
    def test_expedia_hotel_search(self, browser_context):
        timings = {}
        page = browser_context.new_page()

        with timed("1_navigate", timings):
            page.goto(
                "https://www.expedia.com/Hotel-Search?"
                "destination=Los+Gatos%2C+California&startDate=2026-04-11&endDate=2026-04-14&rooms=1&adults=2",
                wait_until="domcontentloaded", timeout=45000
            )
            time.sleep(5)

        with timed("2_verify_results", timings):
            text = page.evaluate("document.body.innerText.substring(0,500)")
            has_results = "hotel" in text.lower() or "property" in text.lower() or "night" in text.lower()

        with timed("3_click_hotel", timings):
            page.evaluate("""(function(){
                var cards=document.querySelectorAll('[data-stid*=property-listing],a[href*="/hotel/"],[class*=PropertyCard]');
                if(cards.length>0){
                    var link=cards[0].querySelector('a')||cards[0];
                    link.click();
                }
            })()""")
            time.sleep(3)

        timings["total"] = sum(timings.values())
        url = page.evaluate("window.location.href")
        page.close()

        print("\n" + "=" * 60)
        print("EXPEDIA — PLAYWRIGHT (Chromium headless)")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  Has results: {has_results}")
        print(f"  URL: {url[:80]}")
        print("=" * 60)
