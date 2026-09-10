import json
from pathlib import Path

ICI = Path(__file__).resolve().parent
content = (ICI / 'maquette_autonome.html').read_text(encoding='utf-8')
start = content.find('<script type="__bundler/template">') + 34
end = content.find('</script>', start)
if start > 34:
    template = json.loads(content[start:end])
    with open(ICI / 'template_extracted.json', 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=2)
    print("Template extracted to template_extracted.json")
else:
    print("Template not found")
