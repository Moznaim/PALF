import csv
import json

features = []
with open(r'C:/Users/erwin/.gemini/antigravity/brain/dabfc264-9f08-4c94-9695-8648aca3b361/.user_uploaded/media_1794083162501_96d977e4.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        features.append(row)

labels = {}
with open(r'C:/Users/erwin/.gemini/antigravity/brain/dabfc264-9f08-4c94-9695-8648aca3b361/.user_uploaded/media_1794083162499_55874b7e.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        labels[row['filename']] = {
            'cleaning_grade': row['cleaning_grade'],
            'texture_label': row['texture_label'],
            'pns_grade_code': row['pns_grade_code'],
            'class': 0 if row['texture_label'] == 'soft' else (1 if row['texture_label'] == 'medium_soft' else 2)
        }

print(f"Loaded {len(features)} image feature rows and {len(labels)} label rows.")

# Class mapping:
# class 0: soft / Excellent / PID-1
# class 1: medium-soft / Good / PID-2
# class 2: medium-coarse / Fair / PID-3 / PID-4

# Let's inspect the top rule: orientation_spread_deg_regional_mean
# Rule text:
# |--- orientation_spread_deg_regional_mean <= 23.455670
# |   |--- orientation_spread_deg_regional_mean <= 22.235450
# |   |   |--- class: 0
# |   |--- orientation_spread_deg_regional_mean >  22.235450
# |   |   |--- class: 0
# |--- orientation_spread_deg_regional_mean >  23.455670
# |   |--- orientation_spread_deg_regional_mean <= 27.049147
# |   |   |--- class: 2
# |   |--- orientation_spread_deg_regional_mean >  27.049147
# |   |   |--- class: 1

def predict_orientation_spread_regional_mean(val):
    if val <= 23.455670:
        return 0, ["orientation_spread_deg_regional_mean <= 23.455670"]
    else:
        if val <= 27.049147:
            return 2, ["orientation_spread_deg_regional_mean > 23.455670", "orientation_spread_deg_regional_mean <= 27.049147"]
        else:
            return 1, ["orientation_spread_deg_regional_mean > 23.455670", "orientation_spread_deg_regional_mean > 27.049147"]

correct = 0
matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
for row in features:
    fname = row['filename']
    true_cls = labels[fname]['class']
    val = float(row['orientation_spread_deg_regional_mean'])
    pred_cls, path = predict_orientation_spread_regional_mean(val)
    matrix[true_cls][pred_cls] += 1
    if pred_cls == true_cls:
        correct += 1

print(f"Top Rule Accuracy on 54 samples: {correct}/54 = {correct/54:.4f}")
print("Confusion Matrix (Rows=True [0=Soft, 1=Med-Soft, 2=Med-Coarse], Cols=Pred):")
for r in matrix:
    print(r)


def predict_gabor_anisotropy(val):
    if val <= 0.454447:
        return 1, ["gabor_response_anisotropy <= 0.454447"]
    elif val <= 0.545935:
        return 2, ["gabor_response_anisotropy > 0.454447", "gabor_response_anisotropy <= 0.545935"]
    else:
        return 0, ["gabor_response_anisotropy > 0.545935"]

correct = 0
for row in features:
    fname = row['filename']
    true_cls = labels[fname]['class']
    val = float(row['gabor_response_anisotropy'])
    pred_cls, path = predict_gabor_anisotropy(val)
    if pred_cls == true_cls:
        correct += 1

print(f"Gabor Anisotropy Accuracy on 54 samples: {correct}/54 = {correct/54:.4f}")


def predict_orientation_spread_deg(val):
    if val <= 22.552517:
        return 0, ["orientation_spread_deg <= 22.552517"]
    elif val <= 27.794097:
        return 2, ["orientation_spread_deg > 22.552517", "orientation_spread_deg <= 27.794097"]
    else:
        return 1, ["orientation_spread_deg > 27.794097"]

correct = 0
for row in features:
    fname = row['filename']
    true_cls = labels[fname]['class']
    val = float(row['orientation_spread_deg'])
    pred_cls, path = predict_orientation_spread_deg(val)
    if pred_cls == true_cls:
        correct += 1

print(f"Whole Bundle Orientation Spread Accuracy on 54 samples: {correct}/54 = {correct/54:.4f}")
