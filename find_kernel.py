import json

with open(r'C:/Users/erwin/.gemini/antigravity/brain/dabfc264-9f08-4c94-9695-8648aca3b361/.system_generated/logs/transcript_full.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        for sub in ['getGaborKernel', 'ksize', 'lambd', 'coherence']:
            if sub in line:
                obj = json.loads(line)
                content = str(obj.get('content', ''))
                idx = content.find(sub)
                if idx != -1:
                    print(f"Match {sub} in step {obj.get('step_index')}:")
                    print(content[max(0, idx-100):min(len(content), idx+200)])
                    print("="*60)
