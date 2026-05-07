#include "WebInput.h"
#if ENABLE_WEB_CONTROLLER
#include <WiFi.h>
#include <WebServer.h>
#include <string.h>
#endif

namespace WebInput
{
#if ENABLE_WEB_CONTROLLER
static const char *kSsid = "Mofongo32";
static const char *kPass = "mofongo32";

static WebServer s_server(80);
static bool s_down[BTN_MAX] = {};
static bool s_pressed[BTN_MAX] = {};

static int btn_from_name(const String &name)
{
  if(name == "up") return BTN_UP;
  if(name == "down") return BTN_DOWN;
  if(name == "left") return BTN_LEFT;
  if(name == "right") return BTN_RIGHT;
  if(name == "a") return BTN_A;
  if(name == "b") return BTN_B;
  if(name == "x") return BTN_X;
  if(name == "y") return BTN_Y;
  if(name == "start") return BTN_START;
  if(name == "select") return BTN_SELECT;
  if(name == "l") return BTN_L;
  if(name == "r") return BTN_R;
  return -1;
}

static void set_button(int b, bool isDown)
{
  if(b < 0 || b >= BTN_MAX)
    return;
  if(isDown && !s_down[b])
    s_pressed[b] = true;
  s_down[b] = isDown;
}

static const char *kPage = R"HTML(
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body { margin:0; font-family:monospace; background:#384F3E; color:#fff; }
.wrap { display:flex; flex-wrap:wrap; gap:12px; padding:16px; justify-content:center; }
.pad { display:grid; grid-template-columns:repeat(3,64px); grid-template-rows:repeat(3,64px); gap:8px; }
.btn { width:64px; height:64px; background:#5B8065; border:2px solid #8CAD92; display:flex; align-items:center; justify-content:center; user-select:none; }
.btn:active { background:#8CAD92; color:#000; }
.col { display:flex; flex-direction:column; gap:12px; }
.wide { width:140px; height:48px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="pad">
    <div></div>
    <div class="btn" data-btn="up">UP</div>
    <div></div>
    <div class="btn" data-btn="left">LEFT</div>
    <div></div>
    <div class="btn" data-btn="right">RIGHT</div>
    <div></div>
    <div class="btn" data-btn="down">DOWN</div>
    <div></div>
  </div>
  <div class="col">
    <div class="btn" data-btn="x">X</div>
    <div class="btn" data-btn="y">Y</div>
    <div class="btn" data-btn="a">A</div>
    <div class="btn" data-btn="b">B</div>
  </div>
  <div class="col">
    <div class="btn" data-btn="l">L</div>
    <div class="btn" data-btn="r">R</div>
    <div class="btn wide" data-btn="start">START</div>
    <div class="btn wide" data-btn="select">SELECT</div>
  </div>
</div>
<script>
function send(btn, down) {
  fetch(`/input?btn=${btn}&down=${down ? 1 : 0}`);
}
document.querySelectorAll('.btn').forEach(b => {
  const name = b.dataset.btn;
  const down = () => send(name, 1);
  const up = () => send(name, 0);
  b.addEventListener('mousedown', down);
  b.addEventListener('mouseup', up);
  b.addEventListener('mouseleave', up);
  b.addEventListener('touchstart', e => { e.preventDefault(); down(); });
  b.addEventListener('touchend', e => { e.preventDefault(); up(); });
});
</script>
</body>
</html>
)HTML";

void begin()
{
  WiFi.mode(WIFI_AP);
  WiFi.softAP(kSsid, kPass);

  s_server.on("/", []() { s_server.send(200, "text/html", kPage); });
  s_server.on("/input", []()
  {
    String btn = s_server.arg("btn");
    String down = s_server.arg("down");
    int b = btn_from_name(btn);
    bool isDown = (down == "1" || down == "true");
    set_button(b, isDown);
    s_server.send(200, "text/plain", "ok");
  });
  s_server.begin();
}

void handle()
{
  s_server.handleClient();
}

bool down(Button b)
{
  if(b < 0 || b >= BTN_MAX)
    return false;
  return s_down[b];
}

bool pressed(Button b)
{
  if(b < 0 || b >= BTN_MAX)
    return false;
  bool v = s_pressed[b];
  if(v)
    s_pressed[b] = false;
  return v;
}
#else
void begin() {}
void handle() {}
bool down(Button) { return false; }
bool pressed(Button) { return false; }
#endif
}
