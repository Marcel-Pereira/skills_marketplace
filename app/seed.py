"""Fixed list of categories and skills. Users can only choose from these.

Run with `flask --app app seed`. Safe to run many times: it only adds what is missing.
To add a skill or category, edit CATALOG below and run the command again.
Skill names must be unique within a category (the same name may appear in two categories).
"""
from sqlalchemy import select

from app import db
from app.catalog_migration import catalog_transaction, upgrade_legacy_skills
from app.models import Category, Skill

CATALOG = {
    "Programming": [
        "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go", "Rust", "Kotlin",
        "Swift", "PHP", "Ruby", "R", "MATLAB", "SQL", "HTML & CSS", "Bash & Linux", "Git & GitHub",
        "Data Structures & Algorithms", "Object-Oriented Programming", "Software Testing",
        "Frontend Web Development", "Backend Development", "Flask", "Django", "React", "Node.js",
        "Mobile App Development", "Game Development", "REST APIs", "Databases", "Docker",
        "Cloud Computing", "Cybersecurity Basics", "Competitive Programming",
    ],
    "Data & AI": [
        "Data Analysis", "Data Visualization", "Machine Learning", "Deep Learning",
        "Natural Language Processing", "Computer Vision", "Prompt Engineering", "Excel",
        "Google Sheets", "Power BI", "Tableau", "Pandas & NumPy", "Data Cleaning", "A/B Testing",
        "Big Data", "Data Engineering",
    ],
    "Languages": [
        "English", "Spanish", "French", "German", "Italian", "Portuguese", "Mandarin Chinese",
        "Cantonese", "Japanese", "Korean", "Arabic", "Hindi", "Bengali", "Urdu", "Russian",
        "Ukrainian", "Polish", "Turkish", "Dutch", "Swedish", "Greek", "Hebrew", "Persian",
        "Vietnamese", "Thai", "Indonesian", "Swahili", "Latin", "American Sign Language",
    ],
    "Mathematics": [
        "Arithmetic", "Algebra", "Geometry", "Trigonometry", "Pre-Calculus", "Calculus",
        "Linear Algebra", "Discrete Mathematics", "Probability", "Statistics",
        "Differential Equations", "Number Theory", "Mathematical Proofs", "Math Olympiad",
    ],
    "Science": [
        "Physics", "Chemistry", "Organic Chemistry", "Biology", "Genetics", "Neuroscience",
        "Astronomy", "Earth Science", "Environmental Science", "Ecology", "Biochemistry",
        "Microbiology", "Lab Techniques", "Scientific Writing",
    ],
    "Humanities & Social Sciences": [
        "History", "Philosophy", "Psychology", "Sociology", "Political Science", "Economics",
        "Anthropology", "Geography", "Literature", "Linguistics", "Religious Studies",
        "International Relations", "Law Basics", "Ethics", "Art History",
    ],
    "Business & Finance": [
        "Entrepreneurship", "Marketing", "Digital Marketing", "SEO", "Social Media Marketing",
        "Accounting", "Personal Finance", "Investing", "Financial Modeling", "Project Management",
        "Product Management", "Sales", "Negotiation", "Business Strategy", "Leadership",
        "Startups & Fundraising", "E-commerce", "Customer Service", "Supply Chain",
    ],
    "Design": [
        "Graphic Design", "UI/UX Design", "Figma", "Photoshop", "Illustrator", "Canva",
        "3D Modeling", "Blender", "Video Editing", "Motion Graphics", "Animation", "Typography",
        "Logo Design", "Fashion Design", "Interior Design", "Architecture", "Industrial Design",
        "Game Art",
    ],
    "Visual Arts": [
        "Drawing", "Sketching", "Painting", "Watercolor", "Oil Painting", "Acrylic Painting",
        "Digital Art", "Calligraphy", "Sculpting", "Ceramics", "Printmaking",
        "Comics & Manga", "Character Design", "Urban Sketching",
    ],
    "Music": [
        "Guitar", "Bass Guitar", "Piano", "Keyboard", "Violin", "Cello", "Drums", "Ukulele",
        "Saxophone", "Flute", "Trumpet", "Singing", "Music Theory", "Music Production",
        "DJing", "Songwriting", "Ear Training", "Reading Sheet Music",
    ],
    "Performing Arts": [
        "Acting", "Dance", "Ballet", "Salsa", "Tango", "Hip Hop Dance", "Contemporary Dance",
        "Improvisation", "Stand-up Comedy", "Theatre Production", "Voice Acting", "Magic Tricks",
    ],
    "Writing & Communication": [
        "Creative Writing", "Academic Writing", "Technical Writing", "Copywriting", "Journalism",
        "Screenwriting", "Poetry", "Storytelling", "Blogging", "Editing & Proofreading",
        "Public Speaking", "Debate", "Active Listening",
    ],
    "Photography & Film": [
        "Photography", "Portrait Photography", "Landscape Photography", "Photo Editing",
        "Filmmaking", "Cinematography", "Documentary Making", "Podcasting",
        "YouTube Content Creation", "Livestreaming",
    ],
    "Sports": [
        "Soccer", "Basketball", "Tennis", "Padel", "Table Tennis", "Badminton", "Volleyball",
        "Swimming", "Running", "Cycling", "Golf", "Rugby", "Baseball", "Cricket", "Field Hockey",
        "Ice Hockey", "Rock Climbing", "Skateboarding", "Surfing", "Skiing & Snowboarding",
        "Athletics", "Handball",
    ],
    "Martial Arts": [
        "Boxing", "Kickboxing", "Muay Thai", "Karate", "Judo", "Taekwondo",
        "Brazilian Jiu-Jitsu", "Kung Fu", "Capoeira", "Self-Defense", "Fencing",
    ],
    "Fitness & Wellness": [
        "Yoga", "Pilates", "Weightlifting", "Calisthenics", "HIIT", "Stretching & Mobility",
        "Meditation", "Mindfulness", "Nutrition", "Stress Management", "Sleep Habits",
        "Home Workouts", "Running Training Plans",
    ],
    "Health & Medicine": [
        "Anatomy", "Physiology", "Pharmacology", "Nursing Basics", "Public Health",
        "Medical School Prep", "Sports Medicine", "Mental Health Awareness", "Medical Terminology",
        "Physical Therapy Basics",
    ],
    "Cooking & Food": [
        "Cooking", "Baking", "Pastry", "Bread Making", "Vegetarian Cooking", "Vegan Cooking",
        "Grilling & BBQ", "Meal Prep", "Italian Cuisine", "Mexican Cuisine", "Asian Cuisine",
        "Argentinian Cuisine", "Mixology", "Coffee Brewing", "Wine Tasting", "Fermentation",
        "Cake Decorating",
    ],
    "Crafts & DIY": [
        "Knitting", "Crocheting", "Sewing", "Embroidery", "Woodworking", "Jewelry Making",
        "Candle Making", "Origami", "Leatherworking", "Pottery", "Home Repair", "Gardening",
        "Upcycling", "Scrapbooking",
    ],
    "Games & Hobbies": [
        "Chess", "Poker", "Go (board game)", "Board Games", "Rubik's Cube", "Puzzles",
        "Dungeons & Dragons", "Video Game Strategy", "Trivia", "Collecting", "Bird Watching",
        "Fishing", "Astrophotography",
    ],
    "Engineering & Electronics": [
        "Electronics", "Arduino", "Raspberry Pi", "Robotics", "3D Printing", "CAD",
        "Mechanical Engineering", "Electrical Engineering", "Civil Engineering",
        "Aerospace Engineering", "Embedded Systems", "Drone Piloting", "PC Building",
        "Home Automation",
    ],
    "Career & Study Skills": [
        "Resume Writing", "Interview Preparation", "Networking", "LinkedIn", "Career Planning",
        "Time Management", "Productivity", "Study Techniques", "Note-Taking", "Speed Reading",
        "Critical Thinking", "Research Methods", "Presentation Skills", "Exam Prep",
        "Scholarship Applications", "Remote Work", "Freelancing",
    ],
    "Life Skills": [
        "Budgeting", "Home Organization", "Minimalism", "Emotional Intelligence",
        "Conflict Resolution", "First Aid", "Travel Planning", "Moving Abroad",
        "Car Maintenance", "Driving", "Sustainable Living", "Pet Care", "Dog Training",
        "Parenting", "Etiquette", "Dating & Relationships",
    ],
    "Outdoors & Travel": [
        "Hiking", "Camping", "Backpacking", "Trekking", "Kayaking", "Sailing", "Scuba Diving",
        "Orienteering", "Survival Skills", "Cultural Exchange", "Local Tourism Tips",
    ],
    "Education & Teaching": [
        "Tutoring", "Lesson Planning", "Curriculum Design", "Teaching English as a Foreign Language",
        "Early Childhood Education", "Educational Technology", "Classroom Management",
        "Special Education", "Academic Mentoring",
    ],
}


def seed_skills():
    """Upgrade the old catalog and insert missing choices in one transaction."""
    with catalog_transaction(db.engine) as (connection, needs_upgrade):
        categories = Category.__table__
        skills = Skill.__table__
        category_rows = connection.execute(select(categories.c.name, categories.c.id))
        ids_by_name = {name: category_id for name, category_id in category_rows}
        for name in CATALOG:
            if name not in ids_by_name:
                result = connection.execute(categories.insert().values(name=name))
                ids_by_name[name] = result.inserted_primary_key[0]

        if needs_upgrade:
            upgrade_legacy_skills(connection, CATALOG, ids_by_name)

        existing = set(connection.execute(select(skills.c.category_id, skills.c.name)))
        missing = [
            {"category_id": ids_by_name[category], "name": name}
            for category, names in CATALOG.items() for name in names
            if (ids_by_name[category], name) not in existing
        ]
        if missing:
            connection.execute(skills.insert(), missing)
