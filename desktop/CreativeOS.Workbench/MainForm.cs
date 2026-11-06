using Microsoft.Web.WebView2.WinForms;
using Microsoft.Web.WebView2.Core;
using System.Windows.Forms;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text;

namespace CreativeOS.Workbench;

public sealed class MainForm : Form
{
    private readonly WebView2 creativeOsView = new();
    private readonly WebView2 platformView = new();
    private readonly HttpClient http = new();
    private readonly System.Windows.Forms.Timer bridgeTimer = new() { Interval = 2000 };
    private readonly System.Windows.Forms.Timer commandTimer = new() { Interval = 1000 };
    private string sessionId = Guid.NewGuid().ToString();
    private readonly string pageId = "tomato-author";
    private int publishStage;
    private bool publishBusy;

    public MainForm()
    {
        Text = "Creative OS · 发布工作台";
        Width = 1600;
        Height = 1000;
        StartPosition = FormStartPosition.CenterScreen;

        var tabs = new TabControl { Dock = DockStyle.Fill };
        var creativeTab = new TabPage("创作工作台");
        var publicationTab = new TabPage("番茄发布");
        creativeTab.Controls.Add(creativeOsView);
        publicationTab.Controls.Add(platformView);
        tabs.TabPages.Add(creativeTab);
        tabs.TabPages.Add(publicationTab);
        platformView.Dock = DockStyle.Fill;
        creativeOsView.Dock = DockStyle.Fill;
        Controls.Add(tabs);

        Load += async (_, _) =>
        {
            var userData = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "CreativeOS", "WebView2", "tomato");
            var environment = await CoreWebView2Environment.CreateAsync(null, userData);
            await creativeOsView.EnsureCoreWebView2Async(environment);
            await platformView.EnsureCoreWebView2Async(environment);
            platformView.CoreWebView2.WebMessageReceived += (_, e) =>
            {
                try
                {
                    var message = e.TryGetWebMessageAsString();
                    if (!string.IsNullOrWhiteSpace(message))
                        File.WriteAllText(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), message);
                }
                catch { }
            };
            await RestoreBridgeReferenceAsync();
            creativeOsView.Source = new Uri("http://127.0.0.1:8899/");
            platformView.Source = new Uri("https://fanqienovel.com/main/writer/");
            platformView.NavigationCompleted += async (_, _) => await PublishBrowserStateAsync();
            bridgeTimer.Tick += async (_, _) => await PublishBrowserStateAsync();
            bridgeTimer.Start();
            commandTimer.Tick += async (_, _) => await ProcessPublishCommandAsync();
            commandTimer.Start();
        };
    }

    private async Task RestoreBridgeReferenceAsync()
    {
        try
        {
            var state = await http.GetFromJsonAsync<JsonElement>("http://127.0.0.1:8899/api/publication/browser");
            if (state.TryGetProperty("session_id", out var session) && session.GetString() is { Length: > 0 } value)
                sessionId = value;
        }
        catch
        {
            // 8899 尚未启动时保留新的会话标识，后续轮询会重试。
        }
    }

    private async Task PublishBrowserStateAsync()
    {
        if (platformView.CoreWebView2 is null) return;
        try
        {
            var encoded = await platformView.CoreWebView2.ExecuteScriptAsync(@"
                (() => {
                  const body = document.body?.innerText || '';
                  const login = /验证码登录|扫码登录|登录\/注册/.test(body) || /\/login(?:[/?#]|$)/.test(location.href);
                  const numbers = [...body.matchAll(/第\s*(\d+)\s*章/g)].map(x => Number(x[1])).filter(Number.isFinite);
                  const title = document.title || '';
                  const heading = document.querySelector('h1,h2,[class*=title]')?.textContent?.trim() || '';
                  return JSON.stringify({url:location.href,title,ready:document.readyState,login_state:login?'expired':'logged_in',work_title:heading,chapter_number:numbers.length?Math.max(...numbers):null});
                })()");
            var raw = JsonSerializer.Deserialize<string>(encoded);
            if (!string.IsNullOrWhiteSpace(raw))
                await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-dom.txt"), raw);
            var page = raw is null ? null : JsonSerializer.Deserialize<BrowserPage>(raw);
            if (page is null || !page.url.Contains("fanqienovel.com", StringComparison.OrdinalIgnoreCase)) return;
            await http.PostAsJsonAsync("http://127.0.0.1:8899/api/publication/browser", new
            {
                action = "connect",
                platform = "tomato",
                session_id = sessionId,
                page_id = pageId,
                page_url = page.url,
                work_title = page.work_title,
                chapter_number = page.chapter_number,
                platform_work_title = page.work_title,
                platform_chapter_number = page.chapter_number,
                login_state = page.login_state
            });
        }
        catch
        {
            // 浏览器状态不可用时保持页面可用，下一次轮询继续尝试。
        }
    }

    private async Task ProcessPublishCommandAsync()
    {
        if (publishBusy) return;
        publishBusy = true;
        try
        {
            await ProcessPublishCommandCoreAsync();
        }
        finally
        {
            publishBusy = false;
        }
    }

    private async Task<bool> ClickTomatoButtonByTextAsync(string pattern)
    {
        if (platformView.CoreWebView2 is null) return false;
        var script = $@"(() => {{ const re=new RegExp({JsonSerializer.Serialize(pattern)}); const b=[...document.querySelectorAll('button,a,[role=button]')].filter(e=>re.test((e.innerText||e.textContent||'').trim()) && e.offsetParent!==null).pop(); if(!b)return JSON.stringify({{found:false}}); const r=b.getBoundingClientRect(); return JSON.stringify({{found:true,x:r.left+r.width/2,y:r.top+r.height/2}}); }})()";
        var raw = await platformView.CoreWebView2.ExecuteScriptAsync(script);
        var value = JsonSerializer.Deserialize<string>(raw) ?? raw;
        using var doc = JsonDocument.Parse(value);
        if (!doc.RootElement.TryGetProperty("found", out var found) || !found.GetBoolean()) return false;
        var x = doc.RootElement.GetProperty("x").GetDouble();
        var y = doc.RootElement.GetProperty("y").GetDouble();
        var down = JsonSerializer.Serialize(new { type = "mousePressed", x, y, button = "left", clickCount = 1 });
        var up = JsonSerializer.Serialize(new { type = "mouseReleased", x, y, button = "left", clickCount = 1 });
        await platformView.CoreWebView2.CallDevToolsProtocolMethodAsync("Input.dispatchMouseEvent", down);
        await platformView.CoreWebView2.CallDevToolsProtocolMethodAsync("Input.dispatchMouseEvent", up);
        return true;
    }

    private async Task ProcessPublishCommandCoreAsync()
    {
        if (platformView.CoreWebView2 is null) return;
        if (publishStage == 1 && platformView.Source?.ToString().Contains("chapter-manage", StringComparison.OrdinalIgnoreCase) == true)
        {
            var inspect = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const rows=[...document.querySelectorAll('tr,li,div')].filter(e=>/74/.test(e.innerText||'')).slice(0,20).map(e=>({tag:e.tagName,text:(e.innerText||'').trim().slice(0,500),buttons:[...e.querySelectorAll('a,button,[role=button]')].map(x=>(x.innerText||x.textContent||'').trim())})); return JSON.stringify({url:location.href,body:(document.body?.innerText||'').slice(0,3000),rows}); })()");
            var inspectRaw = JsonSerializer.Deserialize<string>(inspect) ?? inspect;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), inspectRaw);
            publishStage = 2;
            return;
        }
        if (publishStage == 2 && platformView.Source?.ToString().Contains("chapter-manage", StringComparison.OrdinalIgnoreCase) == true)
        {
            var delayed = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => JSON.stringify({url:location.href,body:(document.body?.innerText||'').slice(0,5000),iframes:[...document.querySelectorAll('iframe')].map(x=>x.src),links:[...document.querySelectorAll('a,button')].map(x=>(x.innerText||x.textContent||'').trim()).filter(Boolean).slice(0,100)}))()");
            var delayedRaw = JsonSerializer.Deserialize<string>(delayed) ?? delayed;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), delayedRaw);
            publishStage = 3;
            return;
        }
        if (publishStage == 3 && platformView.Source?.ToString().Contains("chapter-manage", StringComparison.OrdinalIgnoreCase) == true)
        {
            var create = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const a=[...document.querySelectorAll('a,button')].find(e=>/新建章节|创建章节/.test((e.innerText||e.textContent||'').trim())); const href=a?.href||'https://fanqienovel.com/main/writer/7645211849524251710/publish/?enter_from=newchapter_0'; location.href=href; return JSON.stringify({stage:3,href}); })()");
            var createRaw = JsonSerializer.Deserialize<string>(create) ?? create;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), createRaw);
            publishStage = 4;
            return;
        }
        if (publishStage == 4 && platformView.Source?.ToString().Contains("publish", StringComparison.OrdinalIgnoreCase) == true)
        {
            var form = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => JSON.stringify({url:location.href,body:(document.body?.innerText||'').slice(0,4000),inputs:[...document.querySelectorAll('input,textarea,[contenteditable=true]')].map(e=>({tag:e.tagName,type:e.type||'',value:e.value||'',ph:e.placeholder||'',name:e.name||'',id:e.id||'',cls:e.className||'',disabled:!!e.disabled,readonly:!!e.readOnly,text:(e.innerText||'').slice(0,100)})),buttons:[...document.querySelectorAll('button,a')].map(e=>(e.innerText||e.textContent||'').trim()).filter(Boolean).slice(-80)}))()");
            var formRaw = JsonSerializer.Deserialize<string>(form) ?? form;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), formRaw);
            publishStage = 5;
            return;
        }
        if (publishStage == 5 && platformView.Source?.ToString().Contains("publish", StringComparison.OrdinalIgnoreCase) == true)
        {
            try
            {
                var localChapter = await File.ReadAllTextAsync(Path.Combine("D:\\田雨\\Creative OS", "projects", "文明升阶", "production", "final_chapters", "chapter_074.md"));
                var title = JsonSerializer.Serialize("第一次拒绝");
                var content = JsonSerializer.Serialize(localChapter.Replace("# 第 74 章：第一次拒绝", "").Trim());
                var contentBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(localChapter.Replace("# 第 74 章：第一次拒绝", "").Trim()));
                var fill = """
(() => {
                  const ins=[...document.querySelectorAll('input')];
                  const set=(el,v)=>{const p=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value'); el.focus(); if(p?.set) p.set.call(el,v); else el.value=v; el.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:'a'})); el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:v})); el.dispatchEvent(new KeyboardEvent('keyup',{bubbles:true,key:'a'})); el.dispatchEvent(new Event('change',{bubbles:true})); el.blur();};
                  if(ins[0]) set(ins[0],'74'); const titleEl=document.querySelector("input[placeholder='请输入标题']") || ins[1]; if(titleEl) set(titleEl,%TITLE%);
                  const ed=document.querySelector('.ProseMirror');
                  const raw=(()=>{const b=atob('%BASE64%'); const a=Uint8Array.from(b,c=>c.charCodeAt(0)); return new TextDecoder().decode(a);})();
                  if(ed){ ed.focus(); ed.innerHTML='<p>'+raw.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\r?\n\r?\n/g,'</p><p>').replace(/\r?\n/g,'<br>')+'</p>'; ed.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:null})); ed.blur(); }
                  // 编辑器受控重渲染可能重置前面的字段，正文写入后再次同步两个字段。
                  const ins2=[...document.querySelectorAll('input')]; const chapterEl=ins2.find(x=>/章节号|chapter/i.test((x.placeholder||'')+' '+(x.name||'')+' '+(x.id||'')) || x.value==='74') || ins2[0]; const titleEl2=document.querySelector("input[placeholder='请输入标题']") || ins2.find(x=>/标题|title/i.test((x.placeholder||'')+' '+(x.name||'')+' '+(x.id||''))) || ins2[1]; if(chapterEl) set(chapterEl,'74'); if(titleEl2) set(titleEl2,%TITLE%);
                  return JSON.stringify({stage:5,inputs:ins.length,filled:!!ed,title:ins[1]?.value||'',chapter:ins[0]?.value||''});
                })()
""".Replace("%TITLE%", title).Replace("%CONTENT%", content).Replace("%BASE64%", contentBase64);
                await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-fill.js"), fill);
                var filled = await platformView.CoreWebView2.ExecuteScriptAsync(fill);
                var filledRaw = JsonSerializer.Deserialize<string>(filled) ?? filled;
                await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-fillraw.txt"), filledRaw);
                await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), filledRaw);
            }
            catch (Exception ex) { await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), JsonSerializer.Serialize(new { ok=false, stage="fill", error=ex.Message })); }
            publishStage = 6;
            return;
        }
        if (publishStage == 6 && platformView.Source?.ToString().Contains("publish", StringComparison.OrdinalIgnoreCase) == true)
        {
            var check = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const ins=[...document.querySelectorAll('input')]; const ed=document.querySelector('.ProseMirror'); const chapter=ins.find(x=>/章节号|chapter/i.test((x.placeholder||'')+' '+(x.name||'')+' '+(x.id||''))) || ins[0]; const title=document.querySelector('input[placeholder=""请输入标题""]') || ins.find(x=>/标题|title/i.test((x.placeholder||'')+' '+(x.name||'')+' '+(x.id||''))) || ins[1]; const next=[...document.querySelectorAll('button,a,[role=button]')].find(e=>(e.innerText||e.textContent||'').trim()==='下一步'); return JSON.stringify({stage:6,inputs:ins.map(x=>({type:x.type,value:x.value,ph:x.placeholder,name:x.name,id:x.id})),chapter:chapter?.value||'',title:title?.value||'',body:(ed?.innerText||'').slice(0,80),next:!!next,url:location.href}); })()");
            var checkRaw = JsonSerializer.Deserialize<string>(check) ?? check;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), checkRaw);
            var titleFix = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const el=document.querySelector('input[placeholder=""请输入标题""]') || document.querySelectorAll('input[type=text]')[1]; if(el && !el.value){ el.focus(); document.execCommand('insertText',false,'第一次拒绝'); el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:'第一次拒绝'})); el.dispatchEvent(new Event('change',{bubbles:true})); el.blur(); } return JSON.stringify({title:el?.value||''}); })()");
            var titleFixRaw = JsonSerializer.Deserialize<string>(titleFix) ?? titleFix;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-titlefix.txt"), titleFixRaw);
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), JsonSerializer.Serialize(new { check = JsonDocument.Parse(checkRaw).RootElement, titleFix = JsonDocument.Parse(titleFixRaw).RootElement }));
            try
            {
                using var doc = JsonDocument.Parse(checkRaw);
                var chapter = doc.RootElement.TryGetProperty("chapter", out var c) ? c.GetString() : null;
                var body = doc.RootElement.TryGetProperty("body", out var bodyEl) ? bodyEl.GetString() : null;
                using var titleDoc = JsonDocument.Parse(titleFixRaw);
                var title = titleDoc.RootElement.TryGetProperty("title", out var t) ? t.GetString() : null;
                if (chapter == "74" && !string.IsNullOrWhiteSpace(body) && body.Length > 50)
                {
                    await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const b=[...document.querySelectorAll('button,a,[role=button]')].find(e=>(e.innerText||e.textContent||'').trim()==='下一步'); if(b)b.click(); })()");
                    publishStage = 8;
                }
            }
            catch { }
            return;
        }
        if (publishStage == 7 && platformView.Source?.ToString().Contains("publish", StringComparison.OrdinalIgnoreCase) == true)
        {
            await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const b=[...document.querySelectorAll('button,a,[role=button]')].find(e=>(e.innerText||e.textContent||'').trim()==='下一步'); if(b) b.click(); })()");
            publishStage = 8;
            return;
        }
        if (publishStage == 8 && platformView.Source?.ToString().Contains("publish", StringComparison.OrdinalIgnoreCase) == true)
        {
            var next = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const b=[...document.querySelectorAll('button,a,[role=button]')].find(e=>(e.innerText||e.textContent||'').trim()==='下一步'); if(b)b.click(); return JSON.stringify({clicked:!!b,url:location.href}); })()");
            var nextRaw = JsonSerializer.Deserialize<string>(next) ?? next;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), nextRaw);
            publishStage = 10;
            return;
        }
        if (publishStage == 10 && platformView.Source?.ToString().Contains("publish", StringComparison.OrdinalIgnoreCase) == true)
        {
            var follow = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => JSON.stringify({url:location.href,body:(document.body?.innerText||'').slice(-5000),fields:[...document.querySelectorAll('input,textarea,select,[contenteditable=true]')].slice(0,20).map(e=>({tag:e.tagName,type:e.type||'',value:e.value||'',ph:e.placeholder||'',text:(e.innerText||'').slice(0,100),required:!!e.required})),buttons:[...document.querySelectorAll('button,a,[role=button]')].map(e=>({text:(e.innerText||e.textContent||'').trim(),disabled:!!e.disabled,outer:e.outerHTML.slice(0,300)})).filter(x=>x.text).slice(-80)}))()");
            var followRaw = JsonSerializer.Deserialize<string>(follow) ?? follow;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), followRaw);
            publishStage = 11;
            return;
        }
        if (publishStage == 11 && platformView.Source?.ToString().Contains("publish", StringComparison.OrdinalIgnoreCase) == true)
        {
            var submit = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const t=document.body?.innerText||''; const b=[...document.querySelectorAll('button,a,[role=button]')].find(e=>(e.innerText||e.textContent||'').trim()==='提交'); if(b)b.click(); return JSON.stringify({clicked:!!b,url:location.href,hasPrompt:t.includes('发布提示')}); })()");
            var submitRaw = JsonSerializer.Deserialize<string>(submit) ?? submit;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), submitRaw);
            publishStage = 12;
            return;
        }
        if (publishStage == 12)
        {
            await Task.Delay(1800);
            var done = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const b=[...document.querySelectorAll('button,a,[role=button]')].find(e=>/确认提交|确认发布|确定/.test((e.innerText||e.textContent||'').trim())); if(b)b.click(); return JSON.stringify({clickedConfirm:!!b,url:location.href,body:(document.body?.innerText||'').slice(0,5000),buttons:[...document.querySelectorAll('button,a,[role=button]')].map(e=>(e.innerText||e.textContent||'').trim()).filter(Boolean).slice(-80)}); })()");
            var doneRaw = JsonSerializer.Deserialize<string>(done) ?? done;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), doneRaw);
            publishStage = 13;
            return;
        }
        if (publishStage == 13)
        {
            var detect = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const b=[...document.querySelectorAll('button,a,[role=button]')].find(e=>(e.innerText||e.textContent||'').trim()==='仅基础检测'); if(b)b.click(); return JSON.stringify({clicked:!!b,url:location.href}); })()");
            var detectRaw = JsonSerializer.Deserialize<string>(detect) ?? detect;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), detectRaw);
            publishStage = 16;
            return;
        }
        if (publishStage == 16)
        {
            await Task.Delay(2500);
            var afterDetect = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => JSON.stringify({url:location.href,body:(document.body?.innerText||'').slice(-2500),buttons:[...document.querySelectorAll('button,a,[role=button]')].map(e=>(e.innerText||e.textContent||'').trim()).filter(Boolean).slice(-40)}))()");
            var afterDetectRaw = JsonSerializer.Deserialize<string>(afterDetect) ?? afterDetect;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), afterDetectRaw);
            publishStage = 17;
            return;
        }
        if (publishStage == 17)
        {
            var final = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const b=[...document.querySelectorAll('button,a,[role=button]')].find(e=>(e.innerText||e.textContent||'').trim()==='开启检测'); if(b)b.click(); return JSON.stringify({clickedDetect:!!b,url:location.href}); })()");
            var finalRaw = JsonSerializer.Deserialize<string>(final) ?? final;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), finalRaw);
            publishStage = 18;
            return;
        }
        if (publishStage == 18)
        {
            var finalState = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const bs=[...document.querySelectorAll('button,a,[role=button]')].filter(e=>(e.innerText||e.textContent||'').trim()==='确定' && (e.offsetParent!==null)); const b=bs[bs.length-1]; if(b)b.click(); return JSON.stringify({clickedConfirm:!!b,url:location.href,body:(document.body?.innerText||'').slice(0,3000),buttons:[...document.querySelectorAll('button,a,[role=button]')].map(e=>(e.innerText||e.textContent||'').trim()).filter(Boolean).slice(-50)}); })()");
            var finalStateRaw = JsonSerializer.Deserialize<string>(finalState) ?? finalState;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), finalStateRaw);
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-stage18.json"), finalStateRaw);
            publishStage = 19;
            return;
        }
        if (publishStage == 19)
        {
            var finalSubmit = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const bs=[...document.querySelectorAll('button,a,[role=button]')].filter(e=>/^(提交|发布|确认发布|确定)$/.test((e.innerText||e.textContent||'').trim()) && e.offsetParent!==null); const b=bs[bs.length-1]; if(b)b.click(); return JSON.stringify({clicked:!!b,count:bs.length,outer:b?.outerHTML||'',url:location.href}); })()");
            var finalSubmitRaw = JsonSerializer.Deserialize<string>(finalSubmit) ?? finalSubmit;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), finalSubmitRaw);
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-stage19.json"), finalSubmitRaw);
            publishStage = 22;
            return;
        }
        if (publishStage == 22)
        {
            await Task.Delay(3000);
            var finalState2 = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const bs=[...document.querySelectorAll('button,a,[role=button]')].filter(e=>/^(提交|发布|确认发布|确定)$/.test((e.innerText||e.textContent||'').trim()) && e.offsetParent!==null); const b=bs[bs.length-1]; if(b)b.click(); return JSON.stringify({clicked:!!b,body:(document.body?.innerText||'').slice(-5000),buttons:[...document.querySelectorAll('button,a,[role=button]')].map(e=>(e.innerText||e.textContent||'').trim()).filter(Boolean).slice(-60)}); })()");
            var finalState2Raw = JsonSerializer.Deserialize<string>(finalState2) ?? finalState2;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), finalState2Raw);
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-stage22.json"), finalState2Raw);
            publishStage = 23;
            return;
        }
        if (publishStage == 23)
        {
            await Task.Delay(5000);
            var nativeClicked = await ClickTomatoButtonByTextAsync("^(确认发布|确认提交)$");
            var pending = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => { const t=document.body?.innerText||''; const bs=[...document.querySelectorAll('button,a,[role=button]')].filter(e=>/^(确认发布|确认提交)$/.test((e.innerText||e.textContent||'').trim()) && e.offsetParent!==null); const b=bs[bs.length-1]; let invoked=false,submitted=false,props=''; if(b){b.focus(); const k=Object.keys(b).find(x=>x.startsWith('__reactProps')); const p=k&&b[k]; props=Object.keys(p||{}).join(','); const f=b.closest('form'); if(f?.requestSubmit){f.requestSubmit(b); submitted=true;} if(p?.onClick){p.onClick({target:b,currentTarget:b,preventDefault(){},stopPropagation(){},nativeEvent:{}}); invoked=true;} else {b.click();}} return JSON.stringify({url:location.href,clicked:!!b,reactInvoked:invoked,formSubmitted:submitted,props,disabled:b?.disabled||false,outer:b?.outerHTML||'',resources:performance.getEntriesByType('resource').map(x=>x.name).filter(x=>/publish|chapter|submit|api/i.test(x)).slice(-30),body:t.slice(-1200)}); })()");
            var pendingRaw = JsonSerializer.Deserialize<string>(pending) ?? pending;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-stage23.json"), JsonSerializer.Serialize(new { nativeClicked, browser = JsonDocument.Parse(pendingRaw).RootElement }));
            // 保留在番茄真实确认界面，交由工作台窗口中的真实按钮完成最终提交。
            // 不能在这里自动跳回章节列表，否则会绕过番茄页面的最终提交状态。
            publishStage = 25;
            return;
        }
        if (publishStage == 24 && platformView.Source?.ToString().Contains("chapter-manage", StringComparison.OrdinalIgnoreCase) == true)
        {
            await Task.Delay(1800);
            var verify3 = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => JSON.stringify({url:location.href,body:(document.body?.innerText||'').slice(0,5000),rows:[...document.querySelectorAll('tr,li,div')].filter(e=>/第\s*74\s*章/.test(e.innerText||'')).slice(0,10).map(e=>(e.innerText||'').trim().slice(0,400))}))()");
            var verify3Raw = JsonSerializer.Deserialize<string>(verify3) ?? verify3;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), verify3Raw);
            publishStage = 25;
            return;
        }
        if (publishStage == 20 && platformView.Source?.ToString().Contains("chapter-manage", StringComparison.OrdinalIgnoreCase) == true)
        {
            await Task.Delay(1800);
            var verify2 = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => JSON.stringify({url:location.href,body:(document.body?.innerText||'').slice(0,5000),rows:[...document.querySelectorAll('tr,li,div')].filter(e=>/第\s*74\s*章/.test(e.innerText||'')).slice(0,10).map(e=>(e.innerText||'').trim().slice(0,400))}))()");
            var verify2Raw = JsonSerializer.Deserialize<string>(verify2) ?? verify2;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), verify2Raw);
            publishStage = 21;
            return;
        }
        if (publishStage == 14 && platformView.Source?.ToString().Contains("chapter-manage", StringComparison.OrdinalIgnoreCase) == true)
        {
            await Task.Delay(1800);
            var verify = await platformView.CoreWebView2.ExecuteScriptAsync(@"(() => JSON.stringify({url:location.href,body:(document.body?.innerText||'').slice(0,5000),rows:[...document.querySelectorAll('tr,li,div')].filter(e=>/第\s*74\s*章/.test(e.innerText||'')).slice(0,10).map(e=>(e.innerText||'').trim().slice(0,400))}))()");
            var verifyRaw = JsonSerializer.Deserialize<string>(verify) ?? verify;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), verifyRaw);
            publishStage = 15;
            return;
        }
        if (publishStage == 0 && File.Exists(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish.json")))
        {
            try
            {
                var command = JsonSerializer.Deserialize<PublishCommand>(await File.ReadAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish.json")));
                File.Delete(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish.json"));
                if (command is null || command.Chapter != 74 || !string.Equals(command.WorkTitle, "文明升阶", StringComparison.Ordinal)) return;
                publishStage = 1;
                await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), "{\"status\":\"navigating\"}");
                await platformView.CoreWebView2.ExecuteScriptAsync("location.href='https://fanqienovel.com/main/writer/chapter-manage/7645211849524251710&%E6%96%87%E6%98%8E%E5%8D%87%E9%98%B6?type=1'");
            }
            catch (Exception ex) { await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), JsonSerializer.Serialize(new { ok=false, error=ex.Message })); }
            return;
        }
        var commandPath = Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish.json");
        if (!File.Exists(commandPath)) return;
        try
        {
            var command = JsonSerializer.Deserialize<PublishCommand>(await File.ReadAllTextAsync(commandPath));
            File.Delete(commandPath);
            if (command is null || command.Chapter != 74 || !string.Equals(command.WorkTitle, "文明升阶", StringComparison.Ordinal))
                return;
            var script = @"(() => {
              const text = document.body?.innerText || '';
              const visible = [...document.querySelectorAll('a,button,[role=button]')].map(e => ({tag:e.tagName,text:(e.innerText||e.textContent||'').trim().slice(0,80),href:e.href||null})).filter(x=>x.text);
              const rows = [...document.querySelectorAll('tr,li,div')].filter(e=>/第\\s*74\\s*章/.test(e.innerText||'')).slice(0,8).map(e=>({tag:e.tagName,text:(e.innerText||'').trim().slice(0,300)}));
              return JSON.stringify({url:location.href,title:document.title,body:text.slice(0,1200),visible,rows});
            })()";
            var encoded = await platformView.CoreWebView2.ExecuteScriptAsync(script);
            var raw = JsonSerializer.Deserialize<string>(encoded) ?? encoded;
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), raw);
        }
        catch (Exception ex)
        {
            await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "creativeos-tomato-publish-result.json"), JsonSerializer.Serialize(new { ok=false, error=ex.Message }));
        }
    }

    private sealed record PublishCommand(string WorkTitle, int Chapter);

    private sealed record BrowserPage(string url, string title, string ready, string login_state, string? work_title, int? chapter_number);
}


