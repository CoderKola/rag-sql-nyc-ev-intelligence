import ast
import os
import subprocess
import sys
import tempfile

ALLOWED_IMPORTS = {"plotly", "pandas", "numpy", "math", "random", "collections", "itertools"}

# Injected into every chart HTML — bridges Plotly click events to the parent frame via postMessage
# and receives highlight commands back to dim non-selected traces.
_PLOTLY_BRIDGE = """
<script>
(function(){
  var _origLws = null;

  function getLocation(pt){
    var n = pt.data && pt.data.name;
    // multi-trace: trace is named after location
    if(n && n !== 'trace 0' && n !== '') return String(n);
    // single-trace: location is x or y axis value
    return pt.x != null ? String(pt.x) : pt.y != null ? String(pt.y) : null;
  }

  function highlight(gd, loc){
    if(!gd || !gd.data) return;
    var n = gd.data.length;
    if(!loc){
      Plotly.restyle(gd, {opacity: 1});
      if(n === 1){
        Plotly.restyle(gd, {'marker.opacity': 1, 'marker.line.width': 0});
      } else if(_origLws){
        Plotly.restyle(gd, {'line.width': _origLws});
      }
      _origLws = null;
      return;
    }
    if(n === 1){
      // single trace: highlight selected bar/point with bold border + dim rest
      var axis = gd.data[0].orientation === 'h' ? gd.data[0].y : gd.data[0].x;
      if(!axis) return;
      var vals = Array.from(axis).map(String);
      Plotly.restyle(gd, {
        'marker.opacity':     [vals.map(function(v){ return v === loc ? 1   : 0.1; })],
        'marker.line.width':  [vals.map(function(v){ return v === loc ? 2.5 : 0;   })],
        'marker.line.color':  [vals.map(function(v){ return v === loc ? '#1d4ed8' : 'rgba(0,0,0,0)'; })]
      });
    } else {
      // multi-trace: dim non-selected + thicken selected line so it pops even if colors are similar
      if(!_origLws) _origLws = gd.data.map(function(t){ return (t.line && t.line.width) || 2; });
      Plotly.restyle(gd, {
        opacity: gd.data.map(function(t){ return t.name === loc ? 1 : 0.1; }),
        'line.width': gd.data.map(function(t, i){
          var o = _origLws[i];
          return t.name === loc ? Math.max(o + 2, 4) : o;
        })
      });
    }
  }

  var _lastPlotly = false;
  function init(){
    var gd = document.querySelector('.js-plotly-plot');
    if(!gd){ setTimeout(init, 200); return; }
    gd.on('plotly_click', function(d){
      _lastPlotly = true;
      if(!d.points || !d.points.length) return;
      var loc = getLocation(d.points[0]);
      window.parent.postMessage({type:'ev_click', location: loc}, '*');
    });
    document.addEventListener('click', function(){
      if(!_lastPlotly) window.parent.postMessage({type:'ev_click', location: null}, '*');
      _lastPlotly = false;
    });
  }
  window.addEventListener('message', function(e){
    if(!e.data || e.data.type !== 'ev_highlight') return;
    var gd = document.querySelector('.js-plotly-plot');
    highlight(gd, e.data.location);
  });
  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init)
    : setTimeout(init, 100);
})();
</script>"""


def _imports_allowed(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    return False
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] not in ALLOWED_IMPORTS:
                return False
    return True


def run_chart_code(code: str) -> dict:
    """Execute Plotly chart code in a subprocess sandbox.

    Returns {"success": bool, "chart_html": str | None, "error": str | None}
    """
    if not _imports_allowed(code):
        return {"success": False, "chart_html": None, "error": "Disallowed imports in chart code"}

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "output.html")
        patched = code.replace("'output.html'", repr(out_path)).replace('"output.html"', repr(out_path))

        script = os.path.join(tmpdir, "chart.py")
        with open(script, "w") as f:
            f.write(patched)

        try:
            proc = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "chart_html": None, "error": "Chart execution timed out"}

        if proc.returncode != 0:
            return {"success": False, "chart_html": None, "error": proc.stderr[:500]}

        if not os.path.exists(out_path):
            return {"success": False, "chart_html": None, "error": "Chart code did not write output.html"}

        with open(out_path) as f:
            html = f.read()
        html = html.replace(
            '</head>',
            '<style>html,body{margin:0;padding:0;overflow:hidden;background:#fff;}</style></head>',
            1
        )
        html = html.replace('</body>', _PLOTLY_BRIDGE + '</body>', 1)
        return {"success": True, "chart_html": html, "error": None}
