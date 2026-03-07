import re
import xml.etree.ElementTree as ET
from invoice import constants as invoice_constants
from elastic_logging.logger import elastic_logger


class FormatXMLDocument:
    """
    A class to format XML invoice documents by modifying accounting party information.
    
    This class provides functionality to replace AccountingCustomerParty blocks and
    fix AccountingSupplierParty names in UBL XML invoice documents.
    
    Attributes:
        UBL_CAC_NS (str): UBL Common Aggregate Components namespace
        UBL_CBC_NS (str): UBL Common Basic Components namespace
    """
    
    # UBL namespace constants
    UBL_CAC_NS = 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
    UBL_CBC_NS = 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    
    def __init__(self):
        """
        Initialize the FormatXMLDocument processor.
        """
        self.namespaces = {
            'cac': self.UBL_CAC_NS,
            'cbc': self.UBL_CBC_NS
        }
    
    def _replace_with_regex(self, xml_file_path: str) -> None:
        """
        Replace the AccountingCustomerParty block in an XML file using regex.

        This method reads the XML file, finds the AccountingCustomerParty block using
        a regex pattern, and replaces it with the constant customer party data.

        Args:
            xml_file_path (str): Path to the XML file to modify

        Raises:
            IOError: If the file cannot be read or written
            Exception: For other unexpected errors during processing
        """
        try:
            # Read the file
            with open(xml_file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            # Pattern to find the entire AccountingCustomerParty block
            pattern = r'<cac:AccountingCustomerParty>.*?</cac:AccountingCustomerParty>'

            # Replace using re.DOTALL to include line breaks
            new_content = re.sub(pattern, invoice_constants.ACCOUNTING_CUSTOMER_PARTY.strip(), content, flags=re.DOTALL)

            # Write the modified file
            with open(xml_file_path, 'w', encoding='utf-8') as file:
                file.write(new_content)

        except Exception as e:
            error_msg = f"Error replacing AccountingCustomerParty in {xml_file_path}: {e}"
            elastic_logger.error(error_msg)
            raise Exception(error_msg)
    
    def _fix_accounting_supplier_party_name(self, xml_file_path: str) -> bool:
        """
        Ensures the AccountingSupplierParty section has exactly one PartyName.
        If it doesn't have any, copies it from RegistrationName in PartyTaxScheme.
        If it has multiple, keeps only the first one and removes the rest.

        Args:
            xml_file_path (str): Path to the XML file to process

        Returns:
            bool: True if changes were made, False if not necessary

        Raises:
            ET.ParseError: If the XML file cannot be parsed
            Exception: For other unexpected errors during processing
        """
        try:
            # Parse the XML
            tree = ET.parse(xml_file_path)
            root = tree.getroot()

            # Find AccountingSupplierParty
            supplier_party = root.find('.//cac:AccountingSupplierParty/cac:Party', self.namespaces)

            if supplier_party is None:
                elastic_logger.warning(f"AccountingSupplierParty not found in: {xml_file_path}")
                return False

            # Find all PartyName elements
            party_names = supplier_party.findall('cac:PartyName', self.namespaces)
            changes_made = False

            if len(party_names) > 1:
                # Keep only the first PartyName and remove the rest
                for party_name in party_names[1:]:
                    supplier_party.remove(party_name)
                changes_made = True
            elif len(party_names) == 0:
                # No PartyName found, create one from RegistrationName
                # Find RegistrationName in PartyTaxScheme
                registration_name_elem = supplier_party.find('.//cac:PartyTaxScheme/cbc:RegistrationName', self.namespaces)

                if registration_name_elem is None or not registration_name_elem.text:
                    elastic_logger.warning(f"RegistrationName not found in AccountingSupplierParty: {xml_file_path}")
                    return False

                registration_name = registration_name_elem.text

                # Create the PartyName element
                party_name_elem = ET.Element(f'{{{self.UBL_CAC_NS}}}PartyName')
                name_elem = ET.SubElement(party_name_elem, f'{{{self.UBL_CBC_NS}}}Name')
                name_elem.text = registration_name

                # Find the position after PartyIdentification to insert
                party_identification = supplier_party.find('cac:PartyIdentification', self.namespaces)

                if party_identification is not None:
                    # Insert after PartyIdentification
                    insert_index = list(supplier_party).index(party_identification) + 1
                else:
                    # If there's no PartyIdentification, insert at the beginning
                    insert_index = 0

                supplier_party.insert(insert_index, party_name_elem)
                changes_made = True

            if changes_made:
                # Save the modified file
                tree.write(xml_file_path, encoding='utf-8', xml_declaration=True)

            return changes_made
            
        except ET.ParseError as e:
            error_msg = f"Error parsing XML {xml_file_path}: {e}"
            elastic_logger.error(error_msg)
            raise ET.ParseError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error processing supplier party in {xml_file_path}: {e}"
            elastic_logger.error(error_msg)
            raise Exception(error_msg)
    
    def process_invoice_xml(self, xml_file_path: str) -> bool:
        """
        Main method to process an invoice XML file by applying all formatting operations.

        This method performs the complete XML formatting workflow:
        1. Replaces the AccountingCustomerParty block with the constant data (The AccountingCustomerParty
        should always be the same, and sometimes providers use bad information about the customer company)
        2. Fixes the AccountingSupplierParty by adding PartyName if missing

        Args:
            xml_file_path (str): Path to the XML file to process

        Returns:
            bool: True if supplier party modifications were made, False otherwise.
                Note: Customer party replacement is always attempted.

        Raises:
            IOError: If the file cannot be read or written
            ET.ParseError: If the XML file cannot be parsed
            Exception: For other unexpected errors during processing
        """
        # Step 1: Replace AccountingCustomerParty block
        self._replace_with_regex(xml_file_path)

        # Step 2: Fix AccountingSupplierParty name if needed
        supplier_modified = self._fix_accounting_supplier_party_name(xml_file_path)

        return supplier_modified


