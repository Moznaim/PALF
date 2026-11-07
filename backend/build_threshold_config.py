import csv
import json
import re

rule_details_path = r'C:/Users/erwin/.gemini/antigravity/brain/dabfc264-9f08-4c94-9695-8648aca3b361/.user_uploaded/media_1794083162498_8c9357e4.csv'
candidate_path = r'C:/Users/erwin/.gemini/antigravity/brain/dabfc264-9f08-4c94-9695-8648aca3b361/.user_uploaded/media_1794083162494_4d83d3f6.csv'

# Class mapping:
# 0 -> soft / Excellent / PID-1
# 1 -> medium_soft / Good / PID-2
# 2 -> medium_coarse / Fair / PID-3 / PID-4

CLASS_MAP = {
    0: {"texture_label": "soft", "display_name": "Soft", "associated_grade": "Excellent", "pns_code": "PID-1"},
    1: {"texture_label": "medium_soft", "display_name": "Medium-soft", "associated_grade": "Good", "pns_code": "PID-2"},
    2: {"texture_label": "medium_coarse", "display_name": "Medium-coarse", "associated_grade": "Fair", "pns_code": "PID-3 / PID-4"}
}

candidates = {}
with open(candidate_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        feat = row['feature']
        splits = [float(s.strip()) for s in row['candidate_split_values'].split('|') if s.strip()]
        candidates[feat] = {
            "splits": splits,
            "number_of_splits": int(row['number_of_splits']),
            "cv_balanced_accuracy": float(row['grouped_cv_balanced_accuracy_mean']),
            "cv_macro_f1": float(row['grouped_cv_macro_f1_mean']),
            "threshold_source": row['threshold_source']
        }

rules = {}
with open(rule_details_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        feat = row['feature']
        raw_rules = row['rules']
        rules[feat] = {
            "raw_rules": raw_rules,
            "cv_balanced_accuracy": float(row['cv_balanced_accuracy']),
            "cv_macro_f1": float(row['cv_macro_f1']),
            "candidate_meta": candidates.get(feat, {})
        }

output_config = {
    "version": "1.0",
    "description": "Candidate texture threshold rules derived from 54 inspector-labeled PALF specimens (PNS/BAFS 318:2021 Table 3 alignment)",
    "disclaimer": "Experimental candidate reference comparison · Does not determine or alter deep learning model classification",
    "class_definitions": CLASS_MAP,
    "primary_rule": "orientation_spread_deg_regional_mean",
    "fallback_rule": "orientation_spread_deg",
    "feature_rules": rules
}

out_path = r'backend/config/palf_texture_threshold_rules.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output_config, f, indent=2)

print(f"Saved texture threshold config with {len(rules)} feature rules to {out_path}.")
