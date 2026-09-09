import json
content = open(r'I:\IA\Bot Discord\dashboard\design_v2\maquette_autonome.html', 'r', encoding='utf-8').read()
start = content.find('<script type="__bundler/template">') + 34
end = content.find('</script>', start)
if start > 34:
    template = json.loads(content[start:end])
    with open('template_extracted.json', 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=2)
    print("Template extracted to template_extracted.json")
else:
    print("Template not found")
