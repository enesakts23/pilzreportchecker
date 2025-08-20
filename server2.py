from flask import Flask, request, jsonify
import os
from werkzeug.utils import secure_filename
from espe_report_checker import ESPEReportAnalyzer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = 'temp_uploads_espe'
ALLOWED_EXTENSIONS = {'pdf'}

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/espe-report', methods=['POST'])
def analyze_espe_report():
    try:
        # Check if a file was sent in the request
        if 'file' not in request.files:
            return jsonify({
                'error': 'No file provided',
                'message': 'Please provide a PDF file in the request'
            }), 400

        file = request.files['file']

        # Check if a file was selected
        if file.filename == '':
            return jsonify({
                'error': 'No file selected',
                'message': 'Please select a file to upload'
            }), 400

        # Check if the file is allowed
        if not allowed_file(file.filename):
            return jsonify({
                'error': 'Invalid file type',
                'message': 'Only PDF files are allowed'
            }), 400

        try:
            # Secure the filename and save the file
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Initialize analyzer and analyze the ESPE report
            analyzer = ESPEReportAnalyzer()
            
            # For ESPE analysis, we need both PDF and criteria file
            # The criteria file should be in the same directory or we can use None
            docx_path = None  # Can be None if not needed or specify path to criteria file
            
            report = analyzer.generate_detailed_report(filepath, docx_path)

            # Clean up - remove the temporary file
            try:
                os.remove(filepath)
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {filepath}: {e}")

            # Check if there was an error in the analysis
            if "error" in report:
                return jsonify({
                    'error': 'Analysis failed',
                    'message': report['error']
                }), 500

            # Tam detaylı raporu döndür (espe_report_checker.py gibi)
            detailed_report = {
                'success': True,
                'analiz_tarihi': report.get('analiz_tarihi'),
                'dosya_bilgileri': report.get('dosya_bilgileri'),
                'tarih_gecerliligi': report.get('tarih_gecerliligi'),
                'cikarilan_degerler': report.get('cikarilan_degerler'),
                'kategori_analizleri': report.get('kategori_analizleri'),
                'puanlama': report.get('puanlama'),
                'oneriler': report.get('oneriler'),
                'ozet': report.get('ozet')
            }
            return jsonify(detailed_report), 200

        except Exception as e:
            # Clean up in case of error
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass

            logger.error(f"Error analyzing ESPE report: {str(e)}")
            return jsonify({
                'error': 'Analysis failed',
                'message': str(e)
            }), 500

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({
            'error': 'Server error',
            'message': str(e)
        }), 500

@app.route('/api/espe-health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'ESPE Report Analysis Service is running',
        'service': 'ESPE Report Analyzer'
    }), 200

@app.route('/api/espe-info', methods=['GET'])
def service_info():
    return jsonify({
        'service': 'ESPE Report Analysis API',
        'version': '1.0.0',
        'description': 'API for analyzing ESPE (Electro-Sensitive Protective Equipment) reports',
        'endpoints': {
            '/api/espe-report': 'POST - Upload and analyze ESPE report PDF',
            '/api/espe-health': 'GET - Health check',
            '/api/espe-info': 'GET - Service information'
        },
        'supported_formats': ['PDF'],
        'max_file_size': '16MB'
    }), 200

if __name__ == '__main__':
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    logger.info("Starting ESPE Report Analysis Server on port 5003...")
    app.run(debug=True, host='0.0.0.0', port=5003)
