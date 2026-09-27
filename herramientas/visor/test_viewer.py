import asyncio, sys, os, json
from playwright.async_api import async_playwright
ROOT = os.path.abspath("_npm/package")
URL = "http://127.0.0.1:8765/index.html"
OUT = "shots"
async def route_cdn(route):
    u = route.request.url
    p = u.split("three@0.160.0/", 1)[1].split("?")[0]
    f = os.path.join(ROOT, p)
    if os.path.exists(f):
        await route.fulfill(path=f, content_type="application/javascript")
    else:
        await route.fulfill(status=404, body="nf")
async def run(name, vw, vh, dsf, mobile, scheme, steps):
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist","--enable-unsafe-swiftshader"])
        ctx = await b.new_context(viewport={"width":vw,"height":vh}, device_scale_factor=dsf, is_mobile=mobile, has_touch=mobile, color_scheme=scheme)
        page = await ctx.new_page()
        errs = []
        page.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type in ("error","warning") else None)
        page.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        await page.route("https://cdn.jsdelivr.net/**", route_cdn)
        await page.goto(URL)
        await page.wait_for_function("window.__viewer !== undefined", timeout=60000)
        await page.wait_for_timeout(2500)
        for st in steps:
            await st(page)
        sw = await page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        print(name, "scrollWidth/innerWidth", sw)
        errs=[e for e in errs if "GPU stall" not in e]; print(name, "console:", errs if errs else "sin errores")
        await b.close()

async def shot(page, n):
    await page.wait_for_timeout(1300)
    await page.screenshot(path=f"{OUT}/{n}.png")
    print("shot", n)
def S(n): return lambda p: shot(p, n)
def J(js, wait=0):
    async def f(p):
        await p.evaluate(js)
        if wait: await p.wait_for_timeout(wait)
    return f
async def tap_el(page, idx):
    xy = await page.evaluate(f"window.__viewer.project({idx})")
    await page.mouse.click(xy[0], xy[1]) if False else await page.touchscreen.tap(xy[0], xy[1])
def T(idx): return lambda p: tap_el(p, idx)
async def click(page, sel): await page.click(sel)
def C(sel): return lambda p: click(p, sel)
async def mclick(page, idx):
    xy = await page.evaluate(f"window.__viewer.project({idx})"); await page.mouse.click(xy[0], xy[1])
def MC(idx): return lambda p: mclick(p, idx)

which = sys.argv[1] if len(sys.argv) > 1 else "all"
FIND = "window.__viewer.ELS.findIndex(e=>e.c==='%s' && e.lg===%d)"
async def main():
    if which in ("all","m"):
        await run("mobile", 390, 844, 2, True, "light", [
            S("m1_home"),
            C('[data-tool=levels]'), S("m2_levels"),
            C('[data-tool=levels]'), C('[data-tool=steel]'), S("m3_steelpanel"),
            C('[data-tool=steel]'),
            J("window.__viewer.setView('front',1)", 1200), S("m4_front"),
            J("window.__viewer.setView('iso',1)", 1200),
            J(f"window.__tapIdx={FIND % ('columna',1)}"),
            lambda p: p.evaluate("0"),
        ])
    if which in ("all","m2"):
        async def tapcol(p):
            idx = await p.evaluate(FIND % ('columna', 2))
            await p.evaluate("window.__viewer.S.level=2; window.__viewer.S.mode='upto'")
            await p.evaluate("document.querySelectorAll('#lvlList .lvl')[2].click()")
            await p.wait_for_timeout(1500)
            await tap_el(p, idx)
        await run("mobile2", 390, 844, 2, True, "light", [tapcol, S("m5_props"),
            J("window.__viewer.setXray(true)"), S("m6_props_xray"),
            J("document.querySelector('#grab').dispatchEvent(new PointerEvent('pointerdown',{clientY:500,pointerId:1,bubbles:true}));document.querySelector('#grab').dispatchEvent(new PointerEvent('pointerup',{clientY:500,pointerId:1,bubbles:true}))"), S("m7_props_full")])
    if which in ("all","m3"):
        await run("mobile3", 390, 844, 2, True, "dark", [
            C('[data-tool=cut]'), J("document.querySelectorAll('#hSnap .chip')[2].click()"), S("m8a_cutpanel_dark"),
            C('[data-tool=cut]'), S("m8_cut_dark"), J("window.__viewer.setXray(true)"), S("m9_cut_xray"),
            J("window.__viewer.setXray(false); window.__viewer.S.h.on=false; window.__viewer.S.v={on:true,axis:'u',val:6.4,flip:false}; window.__viewer.syncCutUI(); window.__viewer.applyCuts()"), S("m10_vcut"),
            J("window.__viewer.S.v.on=false; window.__viewer.syncCutUI(); window.__viewer.applyCuts()"),
            C('[data-tool=explode]'), J("window.__viewer.setExplode(3); window.__viewer.setView('iso',1)", 1200), S("m11_explode"),
            C('[data-tool=explode]'), C('#btnSum'), S("m12_summary"),
        ])
    if which in ("all","m4"):
        async def dbl(p):
            idx = await p.evaluate(FIND % ('viga', 2))
            xy = await p.evaluate(f"window.__viewer.project({idx})")
            await p.touchscreen.tap(xy[0], xy[1]); await p.wait_for_timeout(120); await p.touchscreen.tap(xy[0], xy[1])
        await run("mobile4", 390, 844, 2, True, "light", [J("window.__viewer.setView('top',1)", 1200), S("m13_plan"),
            J("window.__viewer.setView('side',1)", 1200), S("m14_side"), J("window.__viewer.setView('iso',1)", 1200), dbl, S("m15_dbltap_focus"),
            C('[data-act=iso]'), S("m16_isolate")])
    if which in ("all","d"):
        async def dsel(p):
            idx = await p.evaluate(FIND % ('viga', 3))
            await p.evaluate("document.querySelectorAll('#lvlList .lvl')[3].click()")
            await p.wait_for_timeout(800)
            await mclick(p, idx)
        await run("desktop", 1440, 900, 1, False, "light", [S("d1_home"), dsel, S("d2_select"),
            J("window.__viewer.setView('top',1)", 1200), S("d3_top"),
            C('[data-tool=layers]'), S("d4_layers")])
        await run("desktopdark", 1440, 900, 1, False, "dark", [J("window.__viewer.setSteel(false)"), S("d5_dark_nosteel"),
            J("window.__viewer.setSteel(true);window.__viewer.setView('side',1)",1200), S("d6_side")])
asyncio.run(main())
