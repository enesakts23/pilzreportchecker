from flask import Flask, request, jsonify
import os
from werkzeug.utils import secure_filename
from at_type_inspection_checker import ATTypeInspectionAnalyzer
import logging
import pytesseract

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Tesseract installation check
def check_tesseract_installation():
    """Check if Tesseract is properly installed"""
    try:
        # Try to get Tesseract version
        version = pytesseract.get_tesseract_version()
        logger.info(f"Tesseract OCR kurulu - Sürüm: {version}")
        return True, f"Tesseract v{version}"
    except Exception as e:
        logger.error(f"Tesseract OCR kurulu değil: {e}")
        return False, str(e)

# Check Tesseract on startup
tesseract_available, tesseract_info = check_tesseract_installation()

# Configure upload settings
UPLOAD_FOLDER = 'temp_uploads_at'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/at-declaration', methods=['POST'])
def analyze_at_declaration():
    """AT Uygunluk Beyanı (EC Declaration of Conformity) analiz API endpoint'i"""
    try:
        # Check if a file was sent in the request
        if 'file' not in request.files:
            return jsonify({
                'error': 'No file provided',
                'message': 'Lütfen analiz edilmek üzere bir AT Uygunluk Beyanı dosyası sağlayın'
            }), 400

        file = request.files['file']

        # Check if a file was selected
        if file.filename == '':
            return jsonify({
                'error': 'No file selected',
                'message': 'Lütfen bir dosya seçin'
            }), 400

        # Check if the file is allowed
        if not allowed_file(file.filename):
            return jsonify({
                'error': 'Invalid file type',
                'message': 'Sadece PDF, JPG, JPEG ve PNG dosyaları kabul edilir'
            }), 400

        try:
            # Secure the filename and save the file
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            logger.info(f"AT Uygunluk Beyanı analiz ediliyor: {filename}")

            # Check if file requires OCR (image files or potentially image-based PDFs)
            file_extension = os.path.splitext(filename)[1].lower()
            requires_ocr = file_extension in ['.jpg', '.jpeg', '.png']
            
            # Check Tesseract availability for OCR-requiring files
            if requires_ocr and not tesseract_available:
                # Clean up file first
                try:
                    os.remove(filepath)
                except:
                    pass
                
                return jsonify({
                    'error': 'OCR not available',
                    'message': 'Tesseract OCR kurulu değil. Resim dosyalarını analiz edebilmek için Tesseract kurulumu gereklidir.',
                    'details': {
                        'tesseract_error': tesseract_info,
                        'file_type': file_extension,
                        'requires_ocr': True,
                        'installation_help': {
                            'windows': 'https://github.com/UB-Mannheim/tesseract/wiki adresinden Tesseract indirip kurun',
                            'macos': 'brew install tesseract komutunu çalıştırın',
                            'ubuntu': 'sudo apt-get install tesseract-ocr tesseract-ocr-tur komutunu çalıştırın',
                            'centos': 'sudo yum install tesseract tesseract-langpack-tur komutunu çalıştırın'
                        }
                    }
                }), 400

            # Initialize analyzer and analyze the AT Declaration
            analyzer = ATTypeInspectionAnalyzer()
            report = analyzer.analyze_at_declaration(filepath)

            # Clean up - remove the temporary file
            try:
                os.remove(filepath)
                logger.info(f"Geçici dosya temizlendi: {filename}")
            except Exception as e:
                logger.warning(f"Geçici dosya silinemedi {filepath}: {e}")

            # Check if analysis was successful
            if "error" in report:
                # Check if it's a Tesseract-related error
                if "tesseract" in report.get('error', '').lower():
                    return jsonify({
                        'error': 'OCR Error',
                        'message': 'Tesseract OCR kurulum sorunu. Lütfen sistem yöneticinize başvurun.',
                        'details': {
                            'original_error': report['error'],
                            'tesseract_available': tesseract_available,
                            'tesseract_info': tesseract_info,
                            'solution': 'Tesseract OCR yazılımını kurun ve PATH değişkenine ekleyin'
                        }
                    }), 500
                
                return jsonify({
                    'error': 'Analysis failed',
                    'message': report['error']
                }), 500

            # Return the analysis results
            return jsonify({
                'success': True,
                'report_type': 'AT Uygunluk Beyanı (EC Declaration of Conformity)',
                'analysis_date': report['analysis_date'],
                'file_info': {
                    'filename': filename,
                    'file_format': report['file_info']['file_format'].upper(),
                    'text_length': report['file_info']['text_length'],
                    'detected_language': report['file_info']['detected_language'].upper()
                },
                'summary': {
                    'total_score': report['summary']['total_score'],
                    'percentage': round(report['summary']['percentage'], 1),
                    'status': report['summary']['status'],
                    'status_tr': report['summary']['status_tr'],
                    'critical_missing_count': report['summary']['critical_missing_count'],
                    'report_type': report['summary']['report_type']
                },
                'extracted_values': {
                    'manufacturer_name': report['extracted_values']['manufacturer_name'],
                    'manufacturer_address': report['extracted_values']['manufacturer_address'],
                    'machine_description': report['extracted_values']['machine_description'],
                    'machine_model': report['extracted_values']['machine_model'],
                    'production_year': report['extracted_values']['production_year'],
                    'serial_number': report['extracted_values']['serial_number'],
                    'declaration_date': report['extracted_values']['declaration_date'],
                    'authorized_person': report['extracted_values']['authorized_person'],
                    'position': report['extracted_values']['position'],
                    'applied_standards': report['extracted_values']['applied_standards']
                },
                'category_scores': report['scoring']['category_scores'],
                'critical_missing': report['scoring']['critical_missing'],
                'recommendations': report['recommendations'],
                'detailed_analysis': report['category_analyses']
            }), 200

        except Exception as e:
            # Clean up in case of error
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass

            # Check if it's a Tesseract-related error
            error_msg = str(e).lower()
            if "tesseract" in error_msg:
                logger.error(f"Tesseract OCR hatası: {str(e)}")
                return jsonify({
                    'error': 'OCR System Error',
                    'message': 'Tesseract OCR sistemi bulunamadı veya çalışmıyor',
                    'details': {
                        'error': str(e),
                        'tesseract_available': tesseract_available,
                        'tesseract_info': tesseract_info,
                        'installation_required': True,
                        'help': {
                            'windows': 'https://github.com/UB-Mannheim/tesseract/wiki',
                            'macos': 'brew install tesseract',
                            'linux': 'apt-get install tesseract-ocr tesseract-ocr-tur'
                        }
                    }
                }), 500

            logger.error(f"AT Uygunluk Beyanı analiz hatası: {str(e)}")
            return jsonify({
                'error': 'Analysis failed',
                'message': f'Analiz sırasında hata oluştu: {str(e)}'
            }), 500

    except Exception as e:
        logger.error(f"Server hatası: {str(e)}")
        return jsonify({
            'error': 'Server error',
            'message': f'Sunucu hatası: {str(e)}'
        }), 500

@app.route('/api/at-health', methods=['GET'])
def health_check():
    """AT Declaration API sağlık kontrolü"""
    return jsonify({
        'status': 'healthy',
        'service': 'AT Declaration Analyzer API',
        'message': 'AT Uygunluk Beyanı analiz servisi çalışıyor',
        'version': '1.0',
        'supported_formats': ['PDF', 'JPG', 'JPEG', 'PNG'],
        'upload_folder': UPLOAD_FOLDER,
        'max_file_size': '16MB',
        'directive': '2006/42/EC Machine Directive',
        'system_status': {
            'tesseract_available': tesseract_available,
            'tesseract_info': tesseract_info,
            'ocr_capability': 'Tam OCR desteği' if tesseract_available else 'OCR desteği yok - sadece PDF metin'
        }
    }), 200

@app.route('/api/at-info', methods=['GET'])
def api_info():
    """AT Declaration API bilgileri"""
    return jsonify({
        'api_name': 'AT Uygunluk Beyanı (EC Declaration of Conformity) Analiz API',
        'description': '2006/42/EC Makine Direktifi gereksinimlerine göre AT Uygunluk Beyanı belgelerini analiz eder',
        'directive_compliance': '2006/42/EC Machine Directive',
        'endpoints': {
            'POST /api/at-declaration': {
                'description': 'AT Uygunluk Beyanı belgesi analiz eder',
                'parameters': {
                    'file': 'Analiz edilecek AT Uygunluk Beyanı dosyası (PDF, JPG, JPEG, PNG)'
                },
                'response': 'Detaylı analiz raporu ve uygunluk değerlendirmesi'
            },
            'GET /api/at-health': {
                'description': 'API sağlık durumu kontrolü',
                'response': 'Servis durumu bilgisi'
            },
            'GET /api/at-info': {
                'description': 'API bilgileri ve kullanım kılavuzu',
                'response': 'API dokümantasyonu'
            }
        },
        'analysis_categories': {
            'Kritik Bilgiler': {
                'weight': 60,
                'critical': True,
                'includes': [
                    'Üretici adı',
                    'Üretici adresi', 
                    'Makine tanımı',
                    '2006/42/EC Direktif atfı',
                    'Yetkili imza'
                ]
            },
            'Zorunlu Teknik Bilgiler': {
                'weight': 25,
                'critical': False,
                'includes': [
                    'Üretim yılı',
                    'Seri numarası',
                    'Beyan ifadesi',
                    'Tarih ve yer',
                    'Diğer direktifler (EMC, LVD)'
                ]
            },
            'Standartlar ve Belgeler': {
                'weight': 15,
                'critical': False,
                'includes': [
                    'Uyumlaştırılmış standartlar (EN, ISO, IEC)',
                    'Teknik dosya sorumlusu',
                    'Onaylanmış kuruluş bilgileri'
                ]
            }
        },
        'validation_criteria': {
            'status_levels': {
                'VALID (GEÇERLİ)': 'Kritik eksiklik yok ve %70+ puan',
                'CONDITIONAL (KOŞULLU)': 'Kritik eksiklik yok ve %50-69 puan',
                'INSUFFICIENT (YETERSİZ)': 'Kritik eksiklik yok ama %50 altı puan',
                'INVALID (GEÇERSİZ)': 'Kritik eksiklikler mevcut'
            },
            'critical_requirements': [
                'Üretici/yetkili temsilci adı ve adresi',
                'Makine tanımı ve tip/model bilgisi',
                '2006/42/EC Makine Direktifi referansı',
                'Yetkili kişi imzası ve unvanı'
            ],
            'minimum_score': 70,
            'critical_category_minimum': 80
        },
        'supported_languages': [
            'Türkçe (ana dil)',
            'İngilizce',
            'Otomatik dil tespiti'
        ],
        'features': [
            'PyPDF2 ve OCR ile metin çıkarma',
            'Resim dosyalarından OCR ile metin çıkarma (JPG, PNG)',
            'PDF içindeki resimlerden OCR ile metin çıkarma',
            'Otomatik dil tespiti',
            'Regex tabanlı kritik bilgi çıkarma',
            'Çoklu üretici firma desteği',
            'Kategori bazlı puanlama sistemi',
            'Kritik eksiklik tespiti',
            'Detaylı öneri sistemi',
            '2006/42/EC direktif uyumluluk kontrolü'
        ],
        'extraction_capabilities': {
            'manufacturer_info': [
                'Sibernetik Makina & Otomasyon',
                'Pilz Ireland Industrial Automation',
                'Suzhou Keber Technology Co',
                'Diğer üretici firmalar'
            ],
            'machine_types': [
                'Ford Ecotorq motor sistemleri',
                'Knee pad punching machines',
                'Vibratory surface finishing machines',
                'Genel makine ekipmanları'
            ],
            'address_formats': [
                'Türk adresleri (Demirci Cd. Nilüfer/Bursa)',
                'Uluslararası adresler (Cork/Ireland, Suzhou/China)',
                'Standart adres formatları'
            ]
        },
        'compliance_notes': [
            'Belge 2006/42/EC Makine Direktifi Ek II-A gereksinimlerine göre analiz edilir',
            'AT Uygunluk Beyanı zorunlu bilgiler kontrol edilir',
            'Kritik eksiklikler durumunda belge geçersiz sayılır',
            'Uyumlaştırılmış standart referansları değerlendirilir',
            'Yetkili kişi imzası ve beyan metni zorunludur'
        ]
    }), 200

@app.route('/api/at-validate', methods=['POST'])
def validate_declaration():
    """AT Uygunluk Beyanı hızlı geçerlilik kontrolü"""
    try:
        if 'file' not in request.files:
            return jsonify({
                'error': 'No file provided',
                'message': 'Dosya sağlanmadı'
            }), 400

        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'error': 'No file selected',
                'message': 'Dosya seçilmedi'
            }), 400

        if not allowed_file(file.filename):
            return jsonify({
                'error': 'Invalid file type',
                'message': 'Sadece PDF, JPG, JPEG ve PNG dosyaları kabul edilir'
            }), 400

        # Check OCR requirement for image files
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension in ['.jpg', '.jpeg', '.png'] and not tesseract_available:
            return jsonify({
                'valid': False,
                'error': 'OCR not available for image files',
                'message': 'Resim dosyalarını analiz edebilmek için Tesseract OCR kurulumu gereklidir'
            }), 400

        # Temporary file processing
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            analyzer = ATTypeInspectionAnalyzer()
            report = analyzer.analyze_at_declaration(filepath)
            
            # Clean up
            os.remove(filepath)
            
            if "error" in report:
                return jsonify({
                    'valid': False,
                    'error': report['error']
                }), 500

            # Quick validation response
            is_valid = (report['summary']['status'] in ['VALID', 'CONDITIONAL'] and 
                       report['summary']['critical_missing_count'] == 0)
            
            return jsonify({
                'valid': is_valid,
                'status': report['summary']['status_tr'],
                'score': round(report['summary']['percentage'], 1),
                'critical_missing_count': report['summary']['critical_missing_count'],
                'critical_missing': report['scoring']['critical_missing'],
                'quick_assessment': {
                    'manufacturer_found': report['extracted_values']['manufacturer_name'] != 'Bulunamadı',
                    'machine_description_found': report['extracted_values']['machine_description'] != 'Bulunamadı',
                    'directive_reference_found': 'directive_reference' in report['extracted_values'],
                    'authorized_signature_area': report['extracted_values']['authorized_person'] != 'Bulunamadı'
                }
            }), 200

        except Exception as e:
            # Clean up in case of error
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass
            raise e

    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return jsonify({
            'valid': False,
            'error': f'Doğrulama hatası: {str(e)}'
        }), 500

@app.errorhandler(413)
def too_large(e):
    """Dosya boyutu çok büyük hatası"""
    return jsonify({
        'error': 'File too large',
        'message': 'Dosya boyutu 16MB limitini aşıyor'
    }), 413

@app.errorhandler(400)
def bad_request(e):
    """Kötü istek hatası"""
    return jsonify({
        'error': 'Bad request',
        'message': 'Geçersiz istek'
    }), 400

@app.errorhandler(500)
def internal_error(e):
    """İç sunucu hatası"""
    return jsonify({
        'error': 'Internal server error',
        'message': 'Sunucu hatası oluştu'
    }), 500

if __name__ == '__main__':
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    logger.info("AT Uygunluk Beyanı Analiz API başlatılıyor...")
    logger.info(f"Upload klasörü: {UPLOAD_FOLDER}")
    logger.info(f"Desteklenen formatlar: PDF, JPG, JPEG, PNG")
    logger.info(f"Tesseract OCR durumu: {'Kurulu' if tesseract_available else 'Kurulu değil'}")
    if tesseract_available:
        logger.info(f"Tesseract bilgisi: {tesseract_info}")
    else:
        logger.warning(f"Tesseract OCR sorunu: {tesseract_info}")
        logger.warning("Resim dosyaları analiz edilemeyecek!")
    logger.info(f"Direktif uyumluluğu: 2006/42/EC Machine Directive")
    logger.info("API endpoint'leri:")
    logger.info("  POST /api/at-declaration - AT Uygunluk Beyanı analizi")
    logger.info("  POST /api/at-validate    - Hızlı geçerlilik kontrolü")
    logger.info("  GET  /api/at-health     - Sağlık kontrolü")
    logger.info("  GET  /api/at-info       - API bilgileri")
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=5008, debug=True) 
