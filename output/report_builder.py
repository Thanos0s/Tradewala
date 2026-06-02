import os
import logging
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

# Path to the folder containing Jinja templates
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)

def render_report(picks: dict, report_dir: str = None) -> str:
    """Render an HTML report for the given picks.
    Returns the absolute path to the generated HTML file.
    """
    if report_dir is None:
        report_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'output', 'reports'))
    os.makedirs(report_dir, exist_ok=True)

    template = env.get_template('report_template.html')
    rendered = template.render(
        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        intraday=picks.get('intraday_picks', []),
        high_risk=picks.get('high_risk_picks', []),
        swing=picks.get('swing_picks', []),
    )

    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(report_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(rendered)
    logging.info(f"Report generated at {filepath}")
    return filepath
