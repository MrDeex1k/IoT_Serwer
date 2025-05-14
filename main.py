from ultralytics import YOLO
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
test_image_path = os.path.join(current_dir, "images", "test.jpg")
test2_image_path = os.path.join(current_dir, "images", "test2.jpg")

model = YOLO("yolo12s.pt")

def analyze_image(image_path):
    results = model.predict(image_path, save=False, classes=[0, 16])
    
    people_count = 0
    dogs_count = 0
    
    for result in results:
        boxes = result.boxes
        for box in enumerate(boxes):
            cls_id = int(box[1].cls[0])
            confidence = float(box[1].conf[0])
            
            if cls_id == 0:  # Osoba
                people_count += 1
                print(f"Wykryto człowieka nr {people_count} {confidence*100:.2f}%")
            elif cls_id == 16:  # Pies
                dogs_count += 1
                print(f"Wykryto psa nr {dogs_count} {confidence*100:.2f}%")
    
    return people_count, dogs_count

# Analizuj pierwszy obraz (test.jpg)
print("Analiza obrazu test.jpg:")
people_count1, dogs_count1 = analyze_image(test_image_path)

if people_count1 == 0 and dogs_count1 == 0:
    print("Nie wykryto żadnych ludzi ani psów na obrazie test.jpg")
else:
    if people_count1 == 0:
        print("Nie wykryto żadnych ludzi na obrazie test.jpg")
    if dogs_count1 == 0:
        print("Nie wykryto żadnych psów na obrazie test.jpg")

# Analizuj drugi obraz (test2.jpg)
print("\nAnaliza obrazu test2.jpg:")
people_count2, dogs_count2 = analyze_image(test2_image_path)

if people_count2 == 0 and dogs_count2 == 0:
    print("Nie wykryto żadnych ludzi ani psów na obrazie test2.jpg")
else:
    if people_count2 == 0:
        print("Nie wykryto żadnych ludzi na obrazie test2.jpg")
    if dogs_count2 == 0:
        print("Nie wykryto żadnych psów na obrazie test2.jpg")
