# Open web navegator and wait for 5 seconds

import time
import os
from django.conf import settings
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager
from elastic_logging.logger import elastic_logger


def prepate_firefox_options():
    """
    Prepare Firefox options for the WebDriver.
    """
    firefox_options = FirefoxOptions()
    # Dont show the browser window

    if not settings.SHOW_BROWSER:
        firefox_options.add_argument("--headless")  # Uncomment to run in headless mode
    
    # Set size of the browser window
    firefox_options.add_argument("--width=1920")
    firefox_options.add_argument("--height=1080")

    firefox_options.add_argument("--no-sandbox")
    firefox_options.add_argument("--disable-dev-shm-usage")
    firefox_options.add_argument("--disable-gpu")
    # specify the path to the Firefox binary if needed
    # firefox_options.binary_location = "/usr/bin/firefox"  # Uncomment and set the path if needed

    # Add arguments to make the browser appear less like a bot
    firefox_options.set_preference("dom.webdriver.enabled", False)  # Disable WebDriver flag
    firefox_options.set_preference("useAutomationExtension", False)  # Disable automation extension
    firefox_options.set_preference("privacy.trackingprotection.enabled", True)  # Enable tracking protection
    firefox_options.set_preference("general.useragent.override", "Mozilla/5.0 (X11; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0")  # Set a custom user agent
    # Open the browser with opened console tools
    # firefox_options.add_argument("--devtools")
    return firefox_options


# Set up the Firefox driver
def setup_driver(firefox_options):
    try:
        service = FirefoxService(GeckoDriverManager().install())

        
        driver = webdriver.Firefox(service=service, options=firefox_options)
        return driver
    except Exception as e:
        elastic_logger.error(f"Error setting up Firefox driver: {e}")
        raise


def navigate_to_other_page(driver, url):
    try:
        driver.get(url)
        elastic_logger.debug(f"Navigated to page: {url}")
    except Exception as e:
        elastic_logger.error(f"Error navigating to page: {e}")
        raise

def do_scroll(driver, x, y):
    try:
        scroll_origin = ScrollOrigin.from_viewport(x, y)
        ActionChains(driver)\
        .scroll_from_origin(scroll_origin, 0, 100)\
        .perform()
    except Exception as e:
        elastic_logger.error(f"Error scrolling: {e}")
        raise


def search_table_document_processing(driver):
    # hidden: <div id="tableDocuments_processing" class="dataTables_processing" style="display: none;">Procesando...</div>
    # visible: <div id="tableDocuments_processing" class="dataTables_processing" style="display: block;">Procesando...</div>
    
    max_time = 180  # Maximum time to wait in seconds

    # while the component is visible wait
    while max_time > 0:
        try:
            # Find the processing element
            processing_element = driver.find_element(By.ID, "tableDocuments_processing")
            # Check if the element is visible
            if processing_element.is_displayed():
                elastic_logger.debug("Processing element is visible, waiting...")
                time.sleep(1)  # Wait for 1 second
                max_time -= 1
            else:
                elastic_logger.debug("Processing element is not visible, continuing")
                break
        except Exception as e:
            elastic_logger.error(f"Error finding processing element: {e}")
            break


def download(dian_link, navigate_to, from_date, to_date, invoice_type="Recibidos", invoice_dir="invoices") -> str:
    elastic_logger.info(f"Starting invoice download: {from_date} to {to_date}, type: {invoice_type}")

    # Config downloads to a specific directory
    download_dir = os.path.join(settings.MEDIA_ROOT, 'tmp', invoice_dir)
    elastic_logger.debug(f"Download directory configured: {download_dir}")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    # Set up Firefox options
    firefox_options = prepate_firefox_options()
    
    # Configurar el directorio de descarga 
    ## Set the download directory
    firefox_options.set_preference("browser.download.folderList", 2)  # Use custom download directory
    firefox_options.set_preference("browser.download.dir", str(download_dir))  # Set custom download directory
        
    # Set up the driver
    driver = setup_driver(firefox_options)

    try:
        # Open the page
        navigate_to_other_page(driver, dian_link)
        time.sleep(5)  # Wait for 5 seconds
        
        # Navigate to another page
        navigate_to_other_page(driver, navigate_to)
        
        search_table_document_processing(driver)


        # 1. Hacer click en el input de fechas
        ## Select input with id "dashboard-report-range"
        input_element = driver.find_element(By.ID, "dashboard-report-range")
        input_element.click()

        ## Select text into input and replate it with the next format: "2025-04-01 - 2025-04-26"
        ## Clear the input field
        input_element.clear()

        ## Write date range with the next format: "2025-04-01 - 2025-04-26"
        input_element.send_keys(f"{from_date} - {to_date}")

        ## Press Enter to save the date range
        input_element.send_keys("\n")

        ## To save the date range, click to input with class "form-control"
        save_button = driver.find_element(By.CSS_SELECTOR, "input.form-control")
        save_button.click()
        elastic_logger.info(f"Date range configured: {from_date} - {to_date}")



        # 2. Hacer click en el input de tipo de documento
        ## Click to div (div.btn-group.bootstrap-select.form-control) that has a button with data-id attribute "DocumentTypeId"
        button_tipo_doc = driver.find_element(By.CSS_SELECTOR, "div.btn-group.bootstrap-select.form-control > button[data-id='DocumentTypeId']")
        ## Get parent div element
        parent_div = button_tipo_doc.find_element(By.XPATH, "..")
        ## Click on the parent div
        parent_div.click()
        elastic_logger.debug("Opening document type dropdown")
        time.sleep(1)  # Wait for 1 seconds

        do_scroll(driver, 0, 200)  # Scroll down to make the options visible

        # 3. Hacer click en el elemento de la lista llamado 'invoice_type'
        ## Click to li a with 'data-normalized-text="{invoice_type}"'
        li_element = driver.find_element(By.CSS_SELECTOR, f"li a[data-normalized-text='{invoice_type}']")
        ## Click on the li element
        li_element.click()
        elastic_logger.info(f"Document type selected: {invoice_type}")
        time.sleep(2)  # Wait for 2 seconds
        

        # 4. Hacer click en el botón de busqueda
        ## Click to button with class "btn-radian-success" to navigate to the export page
        export_button = driver.find_element(By.CSS_SELECTOR, "button.btn.btn-success.btn-radian-success")
        export_button.click()
        elastic_logger.info("Starting document search")
        search_table_document_processing(driver)
        
        # 5. Click en botón para mostrar rangos de paginación. Botón "Mostar"
        label_element = driver.find_element(By.XPATH, "//label[contains(text(), 'Mostrar')]")
        select_element = label_element.find_element(By.XPATH, "..").find_element(By.TAG_NAME, "select")
        elastic_logger.debug("Configuring pagination")
        select_element.click()


        # 6. Mostrar 100 resultados para no tener que hacer click en la paginacion
        ## Select the option with text "100"
        option_element = driver.find_element(By.XPATH, "//option[contains(text(), '100')]")
        option_element.click()
        elastic_logger.info("Configured to show 100 results per page")
        search_table_document_processing(driver)


        # 7. Descargar los archivos de la tabla
        ## Find all "a" tags with class "btn btn-xs btn-hover-gosocket add-tooltip" inside a table
        table = driver.find_elements(By.ID, "tableDocuments")
        
        # Encontrar todas las filas del tbody
        rows = table[0].find_elements(By.CSS_SELECTOR, "tbody > tr")

        file_downloaded_count = 0
        elastic_logger.info(f"Starting download of {len(rows)} invoice files")

        for row in rows:
            # Encontrar el botón en la primera columna
            button = row.find_element(By.CSS_SELECTOR, "td button.download-document")

            # Scroll to element to ensure it's in viewport before clicking
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
            time.sleep(0.5)  # Small delay after scroll

            try:
                # Hacer hover y click
                ActionChains(driver).move_to_element(button).click().perform()
            except Exception as e:
                # Fallback: try direct click if move_to_element fails
                elastic_logger.warning(f"Move to element failed, trying direct click: {e}")
                driver.execute_script("arguments[0].click();", button)

            file_downloaded_count += 1
            elastic_logger.debug(f"Downloading file {file_downloaded_count}/{len(rows)}")

            do_scroll(driver, 0, 100)  # Scroll down to make the options visible

            # Wait still the download is completed. verify if the file is downloaded
            max_wait_time = 30  # Maximum wait time in seconds
            wait_time = 0
            while True:
                # Check if the count of files in the download directory has increased
                files = os.listdir(download_dir)
                if len(files) == file_downloaded_count:
                    elastic_logger.debug(f"File downloaded successfully. Total: {len(files)}")
                    break
                time.sleep(1)  # Wait for 1 second before checking again
                wait_time += 1
                if wait_time >= max_wait_time:
                    elastic_logger.warning(f"File download timeout for file {file_downloaded_count}")
                    break

        elastic_logger.info(f"Download completed: {file_downloaded_count} files downloaded")

        # TODO: Dar click en el botón de paginación para descargar más de 100 archivos

    except Exception as e:
        elastic_logger.error(f"Error during download process: {e}")
        download_dir = None
    finally:
        # Close the driver
        driver.quit()
        elastic_logger.debug("Browser driver closed")

    return download_dir



if __name__ == "__main__":
    dian_link = settings.DIAN_LINK
    navigate_to = "https://catalogo-vpfe.dian.gov.co/Document/Received"

    from_date = "2025-04-24"  # Change this to the desired date range
    to_date = "2025-04-24"  # Change this to the desired date range
    invoice_type = "Factura electronica de venta"  # Change this to "Emitidos" if needed
    invoice_dir = f"invoice_{from_date}_{to_date}"  # Change this to the desired download directory
    
    download(dian_link, navigate_to, from_date, to_date, invoice_type, invoice_dir)

