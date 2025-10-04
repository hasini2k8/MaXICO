from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import uuid
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)



# Configure Gemini
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-pro')

# In-memory storage (use a database in production)
transcriptions = []

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "OK", "timestamp": datetime.now().isoformat()})

@app.route('/api/transcriptions', methods=['POST'])
def create_transcription():
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "Text is required"}), 400
        
        # Create transcription record
        transcription = {
            "id": str(uuid.uuid4()),
            "text": data['text'],
            "metadata": {
                "duration": data.get('duration', 0),
                "language": data.get('language', 'en-US'),
                "created_at": datetime.now().isoformat()
            }
        }
        
        # Analyze with Gemini
        analysis = analyze_with_gemini(data['text'])
        transcription['analysis'] = analysis
        
        # Store transcription
        transcriptions.append(transcription)
        
        return jsonify({
            "success": True,
            "data": transcription
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/transcriptions', methods=['GET'])
def get_transcriptions():
    try:
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        
        # Calculate pagination
        start = (page - 1) * limit
        end = start + limit
        
        paginated_transcriptions = transcriptions[start:end]
        
        return jsonify({
            "success": True,
            "data": paginated_transcriptions,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": len(transcriptions),
                "pages": (len(transcriptions) + limit - 1) // limit
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/transcriptions/<transcription_id>', methods=['GET'])
def get_transcription(transcription_id):
    try:
        transcription = next((t for t in transcriptions if t['id'] == transcription_id), None)
        
        if not transcription:
            return jsonify({"error": "Transcription not found"}), 404
        
        return jsonify({
            "success": True,
            "data": transcription
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/transcriptions/<transcription_id>', methods=['DELETE'])
def delete_transcription(transcription_id):
    try:
        global transcriptions
        original_length = len(transcriptions)
        transcriptions = [t for t in transcriptions if t['id'] != transcription_id]
        
        if len(transcriptions) == original_length:
            return jsonify({"error": "Transcription not found"}), 404
        
        return jsonify({
            "success": True,
            "message": "Transcription deleted successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_text():
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "Text is required"}), 400
        
        analysis = analyze_with_gemini(data['text'])
        
        return jsonify({
            "success": True,
            "analysis": analysis
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/summarize', methods=['POST'])
def summarize_text():
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({"error": "Text is required"}), 400
        
        summary = summarize_with_gemini(data['text'])
        
        return jsonify({
            "success": True,
            "summary": summary
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def analyze_with_gemini(text):
    """Analyze transcript with Gemini AI"""
    try:
        prompt = f"""
        Analyze the following meeting transcript and provide insights:

        Transcript: "{text}"

        Please provide:
        1. Key topics discussed
        2. Action items or decisions made
        3. Important participants mentioned
        4. Overall sentiment
        5. Brief summary

        Format your response as JSON with the following structure:
        {{
            "topics": ["topic1", "topic2", ...],
            "action_items": ["item1", "item2", ...],
            "participants": ["person1", "person2", ...],
            "sentiment": "positive/negative/neutral",
            "summary": "brief summary of the meeting"
        }}
        """
        
        response = model.generate_content(prompt)
        
        # Try to parse as JSON, fallback to text if it fails
        try:
            analysis = json.loads(response.text)
        except json.JSONDecodeError:
            analysis = {
                "raw_analysis": response.text,
                "topics": [],
                "action_items": [],
                "participants": [],
                "sentiment": "neutral",
                "summary": response.text[:200] + "..." if len(response.text) > 200 else response.text
            }
        
        return analysis
        
    except Exception as e:
        return {
            "error": f"Analysis failed: {str(e)}",
            "topics": [],
            "action_items": [],
            "participants": [],
            "sentiment": "neutral",
            "summary": "Analysis unavailable"
        }

def summarize_with_gemini(text):
    """Summarize transcript with Gemini AI"""
    try:
        prompt = f"""
        Please provide a concise summary of this meeting transcript:

        "{text}"

        Focus on:
        - Main discussion points
        - Key decisions made
        - Next steps or action items
        
        Keep the summary under 200 words.
        """
        
        response = model.generate_content(prompt)
        return response.text
        
    except Exception as e:
        return f"Summary unavailable: {str(e)}"

if __name__ == '__main__':
    port = int(os.getenv('PORT', 3000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
