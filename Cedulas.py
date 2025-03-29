from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from functools import lru_cache
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from webdriver_manager.chrome import ChromeDriverManager
import os

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _setup_driver():
    try:
        logger.info("Configurando opciones de Chrome...")
        
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        service = Service(ChromeDriverManager().install())
        
        # Configuración específica para AWS
        if os.path.exists('/usr/bin/chromium-browser'):
            logger.info("Usando configuración para AWS...")
            options.binary_location = '/usr/bin/chromium-browser'
            options.add_argument('--ignore-ssl-errors=yes')         
            options.add_argument('--ignore-certificate-errors')       
            options.add_argument('--allow-insecure-localhost')       
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-dev-tools')
            options.add_argument('--remote-debugging-port=9222')
            options.add_argument('--test-type')
            logger.info("Usando chromium-browser")

            from selenium.webdriver.chrome.service import Service as ChromeService
            service = ChromeService('/usr/bin/chromedriver')
        
        driver = webdriver.Chrome(service=service, options=options)
  
        if os.path.exists('/usr/bin/chromium-browser'):
            driver.set_page_load_timeout(90)
            driver.implicitly_wait(45)
        else:
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(15)
        
        logger.info("Driver iniciado exitosamente")
        return driver
        
    except Exception as e:
        logger.error(f"Error al crear el driver: {str(e)}")
        raise

class CedulaValidator:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=3)
        
    def _setup_driver(self):
        return _setup_driver()

    @lru_cache(maxsize=1000)
    def _get_cached_result(self, cache_key):
        pass


    def _generate_cache_key(self, nombre_completo):
        return hashlib.md5(nombre_completo.lower().encode()).hexdigest()


    def buscar_cedula(self, nombre_completo, max_intentos=3):
        logger.info(f"Iniciando búsqueda para: {nombre_completo}")
        cache_key = self._generate_cache_key(nombre_completo)
        
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            logger.info("Resultado encontrado en caché")
            return cached_result

        for intento in range(max_intentos):
            driver = None
            try:
                logger.info(f"Intento {intento + 1} de {max_intentos}")
                driver = self._setup_driver()
                logger.info("Driver configurado exitosamente")
                return self._realizar_busqueda(driver, nombre_completo)
                
            except Exception as e:
                logger.error(f"Error en intento {intento + 1}: {str(e)}")
                if intento == max_intentos - 1:
                    logger.error("Se agotaron los intentos de búsqueda")
                    raise Exception(f"Error después de {max_intentos} intentos: {str(e)}")
                logger.info(f"Esperando 2 segundos antes de reintentar...")
                time.sleep(2)
                
            finally:
                if driver:
                    try:
                        driver.quit()
                        logger.info("Driver cerrado correctamente")
                    except:
                        logger.warning("Error al cerrar el driver")

    def _realizar_busqueda(self, driver, nombre_completo):
        try:
            logger.info("Navegando a la página de búsqueda...")
            driver.get("https://cedulaprofesional.sep.gob.mx/cedula/indexAvanzada.action")
            
            logger.info("Esperando a que la página cargue...")
            wait = WebDriverWait(driver, 20)
            
            partes = nombre_completo.split()
            if len(partes) < 3:
                logger.error("Nombre incompleto proporcionado")
                raise ValueError("El nombre debe incluir al menos nombre y dos apellidos")
                
            apellido_materno = partes[-1]
            apellido_paterno = partes[-2]
            nombres = " ".join(partes[:-2])
            
            logger.info(f"Datos separados - Nombres: {nombres}, Paterno: {apellido_paterno}, Materno: {apellido_materno}")

            logger.info("Llenando campo de nombre...")
            nombre_input = wait.until(EC.presence_of_element_located((By.ID, "nombre")))
            nombre_input.clear()
            nombre_input.send_keys(nombres)
            
            logger.info("Llenando apellido paterno...")
            paterno_input = wait.until(EC.presence_of_element_located((By.ID, "paterno")))
            paterno_input.clear()
            paterno_input.send_keys(apellido_paterno)
            
            logger.info("Llenando apellido materno...")
            materno_input = wait.until(EC.presence_of_element_located((By.ID, "materno")))
            materno_input.clear()
            materno_input.send_keys(apellido_materno)
            
            logger.info("Buscando y haciendo clic en el botón consultar...")
            try:
                consultar_btn = wait.until(EC.element_to_be_clickable(
                    (By.ID, "dijit_form_Button_0_label")
                ))
                logger.info("Botón encontrado por ID")
            except:
                try:
                    consultar_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//span[text()='Consultar']")
                    ))
                    logger.info("Botón encontrado por texto")
                except:
                    consultar_btn = wait.until(EC.element_to_be_clickable(
                        (By.CLASS_NAME, "dijitButtonText")
                    ))
                    logger.info("Boton encontrado por clase")
            
            logger.info("Haciendo clic en el boton...")
            driver.execute_script("arguments[0].click();", consultar_btn)
            
            logger.info("Esperando resultados...")
            time.sleep(5)
            
            resultados = []
            logger.info("Buscando tabla de resultados...")
            
            try:
                logger.info("Esperando que el grid se cargueeee...")
                wait.until(lambda x: len(driver.find_elements(By.CSS_SELECTOR, ".dojoxGridRow")) > 0)
                time.sleep(2)
                
                filas = driver.find_elements(By.CSS_SELECTOR, ".dojoxGridRow:not(.dojoxGridRowOver)")
                
                logger.info(f"Se encontraron {len(filas)} filas")
                
                for fila in filas:
                    celdas = fila.find_elements(By.CSS_SELECTOR, ".dojoxGridCell")
                    if len(celdas) >= 5 and all(celda.text.strip() for celda in celdas[:5]):
                        resultado = {
                            "cedula": celdas[0].text.strip(),
                            "nombre": celdas[1].text.strip(),
                            "primer_apellido": celdas[2].text.strip(),
                            "segundo_apellido": celdas[3].text.strip(),
                            "tipo": celdas[4].text.strip()
                        }
                        resultados.append(resultado)
                        logger.info(f"Resultado encontrado: {resultado}")
                
                return {"status": "success", "resultados": resultados}
                
            except Exception as e:
                logger.error(f"Error al extraer resultados: {str(e)}")
                raise
            
        except Exception as e:
            logger.error(f"Error en la búsqueda: {str(e)}")
            raise

validator = CedulaValidator()

@app.route('/api/validar-cedula', methods=['POST'])
def validar_cedula():
    try:
        logger.info("Nueva solicitud recibida")
        data = request.get_json()

        if not data or 'nombre_completo' not in data or 'cedula' not in data:
            logger.error("Datos incompletos en la solicitud")
            return jsonify({
                "error": "Debe proporcionar nombre_completo y cedula",
                "status": "error"
            }), 400
            
        nombre_completo = data['nombre_completo'].strip().upper()
        cedula_buscar = data['cedula'].strip()
        
        logger.info(f"Procesando solicitud para: {nombre_completo} con cédula: {cedula_buscar}")
     
        resultado_busqueda = validator.buscar_cedula(nombre_completo)
        
        if not resultado_busqueda or not resultado_busqueda.get("resultados"):
            return jsonify({
                "status": "success",
                "mensaje": "No se encontraron resultados para la búsqueda",
                "coincidencia": False,
                "resultados": []
            })

        cedula_encontrada = None
        for resultado in resultado_busqueda["resultados"]:
            cedula_resultado = resultado["cedula"].strip()

            cedula_resultado = resultado["cedula"].strip()
            nombre_resultado = f"{resultado['nombre']} {resultado['primer_apellido']} {resultado['segundo_apellido']}".strip().upper()
            
            if (cedula_resultado == cedula_buscar and 
                (nombre_resultado == nombre_completo or 
                 nombre_completo in nombre_resultado or 
                 nombre_resultado in nombre_completo)):

                cedula_encontrada = resultado
                break
        
        if cedula_encontrada:

            return jsonify({
                "status": "success",
                "mensaje": "Cédula y nombre verificados correctamente",
                "coincidencia": True,
                "datos": cedula_encontrada
            })
        
        return jsonify({
            "status": "success",

            "mensaje": "Los datos proporcionados no coinciden con ningún registro",
            "coincidencia": False
        })
        
    except Exception as e:
        logger.error(f"Error en endpoint: {str(e)}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
