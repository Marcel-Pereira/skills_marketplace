# Made-up data so the screens have something to show before the database exists.
# Once the models are in, the routes read from the database instead and this file goes away.

# Skills shown as chips during onboarding and on the profile. Users can still type their own.
SKILL_OPTIONS = [
    "Python", "JavaScript", "Data Analysis", "Design", "Public Speaking",
    "Writing", "Spanish", "Mandarin", "Guitar", "Photography",
    "Cooking", "Marketing", "Statistics", "Video Editing",
]

# Stands in for whoever is signed in, until real accounts exist.
CURRENT_USER = {"name": "You", "teaches": ["Python", "Statistics"], "learns": ["Spanish", "Guitar", "Design"]}

# Everyone else. Each person lists what they can teach and what they want to learn.
PEOPLE = [
    {"name": "Linh", "teaches": ["Python", "Data Analysis"], "learns": ["Guitar", "Spanish"]},
    {"name": "Mateo", "teaches": ["Spanish", "Guitar"], "learns": ["Python"]},
    {"name": "Jiwoo", "teaches": ["Design", "Photography"], "learns": ["Public Speaking"]},
    {"name": "Anna", "teaches": ["Statistics", "Writing"], "learns": ["Design", "Cooking"]},
    {"name": "Priya", "teaches": ["Public Speaking", "Marketing"], "learns": ["Video Editing"]},
    {"name": "Sam", "teaches": ["JavaScript", "Video Editing"], "learns": ["Mandarin", "Statistics"]},
    {"name": "Wei", "teaches": ["Mandarin", "Cooking"], "learns": ["JavaScript", "Writing"]},
]
