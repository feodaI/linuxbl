"""Shared GTK CSS for the Feodal shell, settings and installer."""

STYLE = b'''
* { font-family: "Noto Sans", "DejaVu Sans", Sans; outline-color: alpha(#6fd3a8, .5); }
window { background: #111317; color: #e6e8eb; }
window.panel { background: #15181d; border-top: 1px solid #242930; }
window.popup { background: #15181d; border: 1px solid #2a3038; }
button { background: transparent; background-image: none; color: #d7dbe0; border: none;
         box-shadow: none; text-shadow: none; -gtk-icon-shadow: none;
         border-radius: 8px; padding: 6px 12px; min-height: 0; min-width: 0; }
button:hover { background: #22272e; }
button:active, button:checked { background: #2a3038; }
button:disabled { color: #5c636c; }
window.panel button { padding: 4px 9px; }
button.icon { padding: 4px 8px; color: #b9c0c8; }
button.icon:hover { color: #ffffff; }
button.menu { padding: 4px 12px; }
button.menu label { color: #6fd3a8; font-weight: bold; letter-spacing: 1px; }
button.task { color: #8f98a3; padding: 4px 10px; border-radius: 6px;
              border-bottom: 2px solid transparent; }
button.task:hover { color: #e6e8eb; }
button.task.active { color: #f2f4f6; background: #1f242b; border-bottom-color: #6fd3a8; }
button.pill { border: 1px solid #2c323b; padding: 2px 8px; font-size: 8.5pt; font-weight: bold; }
button.action { background: #1f242b; border: 1px solid #2a3038; }
button.action:hover { background: #262c34; border-color: #3a424c; }
label.clock { font-weight: bold; }
label.date, label.muted, label.hint { color: #8a939e; }
label.date { font-size: 8pt; }
label.brand { color: #6fd3a8; font-weight: bold; letter-spacing: 1px; }
label.title { font-size: 13pt; font-weight: bold; }
separator.panel-sep { background: #2a3038; min-width: 1px; margin: 9px 4px; }
entry { background: #1b1f25; color: #e6e8eb; border: 1px solid #2a3038; border-radius: 8px;
        box-shadow: none; padding: 8px 10px; caret-color: #6fd3a8; }
entry:focus { border-color: #6fd3a8; }
combobox button, combobox box { background: #1b1f25; border-radius: 8px; }
menu, .menu, .context-menu { background: #1b1f25; color: #e6e8eb; border: 1px solid #2a3038; padding: 4px; }
menuitem { padding: 7px 14px; border-radius: 6px; }
menuitem label { color: #e6e8eb; }
menuitem:hover { background: #262c34; }
tooltip, tooltip.background { background: #1b1f25; color: #e6e8eb; border: 1px solid #2a3038; }
notebook, notebook > stack, viewport, scrolledwindow { background: #111317; color: #e6e8eb; border: none; }
notebook > header { background: #111317; border: none; border-bottom: 1px solid #242930; }
notebook > header > tabs > tab { background: transparent; color: #8a939e; padding: 8px 14px;
                                 border: none; box-shadow: none; }
notebook > header > tabs > tab:hover { color: #e6e8eb; }
notebook > header > tabs > tab:checked { color: #f2f4f6; box-shadow: inset 0 -2px #6fd3a8; }
list, row { background: transparent; color: #e6e8eb; }
row { border-radius: 8px; }
row:hover { background: #1f242b; }
row:selected { background: #1d3830; }
notebook button { background: #1b1f25; border: 1px solid #2a3038; padding: 8px 12px; }
notebook button:hover { background: #242a32; border-color: #3a424c; }
scrollbar { background: transparent; border: none; }
scrollbar slider { background: #2f353e; border-radius: 4px; min-width: 4px; min-height: 4px; }
button.primary { background: #6fd3a8; color: #0d1512; font-weight: bold; padding: 8px 18px; }
button.primary:hover { background: #8fe3bf; }
button.primary:disabled { background: #2a3038; color: #5c636c; }
button.danger { background: #c4525d; color: #ffffff; font-weight: bold; padding: 8px 18px; }
button.danger:hover { background: #d8636e; }
button.danger:disabled { background: #2a3038; color: #5c636c; }
box.sidebar { background: #15181d; border-right: 1px solid #242930; padding: 22px 0; }
label.step { color: #5c636c; padding: 7px 22px; }
label.step.current { color: #f2f4f6; font-weight: bold; box-shadow: inset 3px 0 #6fd3a8; }
label.step.done { color: #8fe3bf; }
label.stage-done { color: #8fe3bf; }
label.lead { color: #aab2bc; }
label.warning { color: #f0b37e; }
label.error { color: #ef7d86; }
box.card { background: #15181d; border: 1px solid #242930; border-radius: 10px; padding: 14px; }
box.notice { background: #2a1c1e; border: 1px solid #5a2c31; border-radius: 10px; padding: 14px; }
row.disk { padding: 6px 4px; }
progressbar trough { background: #1f242b; border-radius: 6px; min-height: 10px; border: none; }
progressbar progress { background: #6fd3a8; border-radius: 6px; min-height: 10px; border: none; }
textview, textview text { background: #0c0e11; color: #aab2bc; font-family: monospace; font-size: 9pt; }
checkbutton { color: #e6e8eb; }
'''
