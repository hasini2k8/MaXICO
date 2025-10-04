import os
import json
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import google.generativeai as genai
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'webm', 'mp4', 'avi', 'mov'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure Gemini API
# Make sure to set your API key as an environment variable
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not found in environment variables!")
    print("Set it with: export GEMINI_API_KEY='your-api-key-here'")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# System prompt for Gemini
SYSTEM_PROMPT = """You are an AI assistant that analyzes a video of a user throwing trash. Your task is to determine if the trash was successfully thrown into the garbage bin. If yes, return "yes"; if not, return "no". Also, classify the trash as one of: "compost", "recyclable", or "trash". Only return the output in JSON format: { "thrown_in_bin": "yes" | "no", "trash_type": "compost" | "recyclable" | "trash" }. Use visual cues from the video to decide if the trash lands in the bin, and classify common household waste correctly. Do not include any extra commentary."""


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_video_with_gemini(video_path):
    """
    Analyze video using Gemini API
    Returns parsed JSON response
    """
    try:
        print(f"Starting video analysis for: {video_path}")
        
        # Initialize Gemini model with the correct format
        # Use the full model path that works with video
        model = genai.GenerativeModel('models/gemini-2.0-flash')
        print(f"Using model: gemini-2.0-flash")
        
        # Upload file using the correct API
        print("Uploading video to Gemini...")
        video_file = genai.upload_file(path=video_path)
        print(f"Upload complete. File name: {video_file.name}")
        
        # Wait for file to be processed
        print("Waiting for video processing...")
        while video_file.state.name == "PROCESSING":
            print("  Still processing...")
            time.sleep(5)
            video_file = genai.get_file(video_file.name)
        
        if video_file.state.name == "FAILED":
            raise Exception("Video processing failed on Gemini servers")
        
        print("Video processed successfully. Generating analysis...")
        
        # Generate content with video and prompt
        response = model.generate_content(
            [video_file, SYSTEM_PROMPT],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
            )
        )
        
        # Get response text
        response_text = response.text.strip()
        print(f"Raw Gemini response:\n{response_text}\n")
        
        # Clean up response text (remove markdown if present)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        # Parse JSON response
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # If direct parsing fails, try to find JSON in the text
            import re
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise ValueError(f"Could not parse JSON from response: {response_text}")
        
        # Validate response structure
        if "thrown_in_bin" not in result or "trash_type" not in result:
            print(f"Warning: Invalid response structure: {result}")
            # Provide default structure
            result = {
                "thrown_in_bin": result.get("thrown_in_bin", "no"),
                "trash_type": result.get("trash_type", "trash"),
                "raw_response": response_text
            }
        
        print(f"Parsed result: {result}")
        
        # Clean up uploaded file
        try:
            genai.delete_file(video_file.name)
            print("Cleaned up temporary file from Gemini")
        except Exception as cleanup_error:
            print(f"Warning: Could not cleanup file: {cleanup_error}")
        
        return result
        
    except Exception as e:
        print(f"ERROR in analyze_video_with_gemini: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "error_type": type(e).__name__
        }


def analyze_video_alternative(video_path):
    """
    Alternative method using direct file upload
    """
    try:
        import google.generativeai.types.file_types as file_types
        
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        print(f"Using alternative upload method for: {video_path}")
        
        # Try using the Files API directly
        file = genai.File.create(
            path=video_path,
            display_name=os.path.basename(video_path)
        )
        
        print(f"File uploaded with URI: {file.uri}")
        
        # Wait for processing
        while file.state.name == "PROCESSING":
            print("Processing video...")
            time.sleep(3)
            file = genai.File.get(file.name)
        
        if file.state.name == "FAILED":
            raise Exception("Video processing failed")
        
        # Generate content
        response = model.generate_content([SYSTEM_PROMPT, file])
        
        response_text = response.text.strip()
        print(f"Raw response: {response_text}")
        
        # Parse JSON
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response_text)
        
        # Cleanup
        try:
            file.delete()
        except:
            pass
        
        return result
        
    except Exception as e:
        print(f"Alternative method also failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": f"All upload methods failed: {str(e)}"}


@app.route('/api/upload', methods=['POST'])
def upload_video():
    """
    Handle video upload and analysis
    """
    try:
        # Check if video file is present
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
        
        video = request.files['video']
        
        if video.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(video.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Save the video file
        filename = secure_filename(video.filename)
        timestamp = int(time.time())
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        video.save(filepath)
        
        print(f"Video saved to: {filepath}")
        
        # Get summary from frontend (optional metadata)
        summary_data = request.form.get('summary')
        if summary_data:
            summary = json.loads(summary_data)
            print(f"Frontend summary: {summary}")
        
        # Analyze video with Gemini
        gemini_result = analyze_video_with_gemini(filepath)
        
        # Return combined response
        response = {
            'success': True,
            'filename': filename,
            'gemini_analysis': gemini_result,
            'message': 'Video uploaded and analyzed successfully'
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze-existing', methods=['POST'])
def analyze_existing_video():
    """
    Analyze an existing video in the uploads folder
    """
    try:
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'error': 'No filename provided'}), 400
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        # Analyze video with Gemini
        gemini_result = analyze_video_with_gemini(filepath)
        
        response = {
            'success': True,
            'filename': filename,
            'gemini_analysis': gemini_result
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        print(f"Analysis error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/list-videos', methods=['GET'])
def list_videos():
    """
    List all videos in the uploads folder
    """
    try:
        files = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if allowed_file(filename):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                files.append({
                    'filename': filename,
                    'size': os.path.getsize(filepath),
                    'created': os.path.getctime(filepath)
                })
        
        return jsonify({'files': files}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    gemini_configured = GEMINI_API_KEY is not None
    return jsonify({
        'status': 'ok',
        'gemini_configured': gemini_configured,
        'upload_folder': app.config['UPLOAD_FOLDER']
    }), 200


if __name__ == '__main__':
    print("="*50)
    print("Flask Backend with Gemini API Integration")
    print("="*50)
    print(f"Upload folder: {UPLOAD_FOLDER}")
    print(f"Gemini API configured: {GEMINI_API_KEY is not None}")
    
    # List available models
    if GEMINI_API_KEY:
        try:
            print("\nAvailable Gemini models:")
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    print(f"  - {model.name}")
        except Exception as e:
            print(f"Could not list models: {e}")
    
    print("="*50)
    app.run(debug=True, port=5000)