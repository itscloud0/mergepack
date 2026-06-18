from __future__ import annotations

from html import escape

from .core import MergePacket


def render_markdown(packet: MergePacket) -> str:
    lines: list[str] = [
        f"# {packet.title}",
        "",
        f"- Source: `{packet.source}`",
        f"- Repo: `{packet.repo}`",
    ]
    if packet.url:
        lines.append(f"- URL: {packet.url}")
    if packet.base or packet.head:
        lines.append(f"- Range: `{packet.base or '?'}..{packet.head or '?'}`")
    lines.extend(
        [
            f"- Files: {packet.stats.get('files', 0)}",
            f"- Additions/deletions: +{packet.stats.get('additions', 0)}/-{packet.stats.get('deletions', 0)}",
            "",
            "## Changed Files",
            "",
            "| File | Role | Status | Delta |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for file in packet.changed_files:
        lines.append(f"| `{file.path}` | {file.role} | {file.status} | +{file.additions}/-{file.deletions} |")

    lines.extend(["", "## Verification Commands", ""])
    lines.extend(f"- `{command}`" for command in packet.commands)

    lines.extend(["", "## Risk Areas", ""])
    lines.extend(f"- {risk}" for risk in packet.risk_areas)

    lines.extend(["", "## Repo Instructions", ""])
    if packet.instructions:
        lines.extend(f"- `{item.path}`: {item.summary}" for item in packet.instructions)
    else:
        lines.append("- No repo instruction files found by mergepack.")

    lines.extend(["", "## Reviewer Checklist", ""])
    lines.extend(f"- [ ] {item}" for item in packet.checklist)

    lines.extend(["", "## Agent-Ready Prompt", "", "````text", packet.agent_prompt, "````", ""])
    return "\n".join(lines)


def render_html(packet: MergePacket) -> str:
    file_rows = "\n".join(
        "<tr>"
        f"<td>{escape(file.path)}</td>"
        f"<td><span class='pill role-{escape(file.role)}'>{escape(file.role)}</span></td>"
        f"<td>{escape(file.status)}</td>"
        f"<td>+{file.additions}/-{file.deletions}</td>"
        "</tr>"
        for file in packet.changed_files
    )
    command_items = "\n".join(f"<li><code>{escape(command)}</code></li>" for command in packet.commands)
    risk_items = "\n".join(f"<li>{escape(risk)}</li>" for risk in packet.risk_areas)
    instruction_items = "\n".join(
        f"<li><strong>{escape(item.path)}</strong>: {escape(item.summary)}</li>"
        for item in packet.instructions
    ) or "<li>No repo instruction files found by mergepack.</li>"
    checklist_items = "\n".join(f"<li>{escape(item)}</li>" for item in packet.checklist)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(packet.title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --text: #1d2327;
      --muted: #667085;
      --line: #d8ddd8;
      --accent: #0f766e;
      --risk: #b42318;
      --code: #111827;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      padding-bottom: 20px;
      margin-bottom: 22px;
    }}
    h1 {{
      font-size: clamp(30px, 5vw, 52px);
      line-height: 1;
      margin: 0 0 14px;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 20px;
      margin: 28px 0 10px;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      color: var(--muted);
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      overflow: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 10px;
      vertical-align: top;
    }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    code {{
      color: var(--code);
      background: #eef2ef;
      border-radius: 4px;
      padding: 1px 4px;
    }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #111827;
      color: #f9fafb;
      border-radius: 8px;
      padding: 14px;
      max-height: 520px;
      overflow: auto;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 0 8px;
      border-radius: 999px;
      background: #e6f4f1;
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }}
    .role-migration, .role-ci, .role-package {{
      background: #fef3f2;
      color: var(--risk);
    }}
    ul {{
      padding-left: 22px;
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>{escape(packet.title)}</h1>
    <div class="meta">
      <div>Source: <code>{escape(packet.source)}</code></div>
      <div>Files: {packet.stats.get("files", 0)}</div>
      <div>Delta: +{packet.stats.get("additions", 0)}/-{packet.stats.get("deletions", 0)}</div>
      <div>Range: <code>{escape(packet.base or "?")}..{escape(packet.head or "?")}</code></div>
    </div>
  </header>

  <section>
    <h2>Changed Files</h2>
    <div class="panel">
      <table>
        <thead><tr><th>File</th><th>Role</th><th>Status</th><th>Delta</th></tr></thead>
        <tbody>{file_rows}</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Verification Commands</h2>
    <div class="panel"><ul>{command_items}</ul></div>
  </section>

  <section>
    <h2>Risk Areas</h2>
    <div class="panel"><ul>{risk_items}</ul></div>
  </section>

  <section>
    <h2>Repo Instructions</h2>
    <div class="panel"><ul>{instruction_items}</ul></div>
  </section>

  <section>
    <h2>Reviewer Checklist</h2>
    <div class="panel"><ul>{checklist_items}</ul></div>
  </section>

  <section>
    <h2>Agent-Ready Prompt</h2>
    <pre>{escape(packet.agent_prompt)}</pre>
  </section>
</main>
</body>
</html>
"""
