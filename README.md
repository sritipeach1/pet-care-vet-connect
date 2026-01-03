# Pet Care Vet Connect Project


vercel : https://pet-care-vet-connect.vercel.app/login
🐾 PetBot AI Setup (Premium Feature)

PetBot AI uses Google Gemini API and is only available for Premium users.

✅ One-time setup steps:
1️⃣ Install dependency
pip install google-generativeai

2️⃣ Add .env file in project root

Create a .env file and add:

GEMINI_API_KEY=your_api_key_here


✅ Example:

GEMINI_API_KEY=AIzaSyB.....

3️⃣ Run schema update (only once)

Make sure your database has the premium columns by running:

python update_schema.py

4️⃣ Start the app
python app.py

