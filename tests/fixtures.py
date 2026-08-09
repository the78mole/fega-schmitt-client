"""Shared XML fixtures for tests - taken verbatim from the appendix of
docs/specs/Schnittstellenbeschreibung_SOAP.pdf ("Beispiel Antwort"), section ANHANG.
"""

EXAMPLE_RESPONSE_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" soap:EncodingStyle="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <a:PRICE_AVAIL_RESPONSE xmlns:a="https://soap.fega.de/soap_priceavail">
      <PREFIX>
        <ESHOP_ID>XXXXX</ESHOP_ID>
        <TRANSACTION_ID>testtest</TRANSACTION_ID>
        <PARTNER_COMPANY>50</PARTNER_COMPANY>
        <PARTNER_COMPANY_PART></PARTNER_COMPANY_PART>
        <PARTNER_PURCHASER>XXXXX</PARTNER_PURCHASER>
        <PARTNER_PURCHASER_GROUP>K</PARTNER_PURCHASER_GROUP>
      </PREFIX>
      <HEADER>
        <REQUEST_CURRENCY>EUR</REQUEST_CURRENCY>
      </HEADER>
      <ITEM_LIST>
        <ITEM>
          <RETURNCODE>I010</RETURNCODE>
          <RETURNCODE_TEXT>Preis und Verf&#252;gbarkeit korrekt ermittelt</RETURNCODE_TEXT>
          <ITEM_IDENT>
            <LINE_ITEM_NUMBER>1</LINE_ITEM_NUMBER>
            <MATERIAL_NUMBER>0815</MATERIAL_NUMBER>
            <REQUEST_QUANTITY>200</REQUEST_QUANTITY>
            <REQUEST_UNIT>MTR</REQUEST_UNIT>
          </ITEM_IDENT>
          <AVAILABILITY_DATA>
            <AVAILABILITY_STATUS>V</AVAILABILITY_STATUS>
            <AVAILABILITY_PARTNER_WAREHOUSE>22</AVAILABILITY_PARTNER_WAREHOUSE>
            <PARTNER_WAREHOUSE_NAME>Zentrallager</PARTNER_WAREHOUSE_NAME>
          </AVAILABILITY_DATA>
          <PRICE_DATA>
            <PRICE_AMOUNT>36.90</PRICE_AMOUNT>
            <NET_AMOUNT>67.54</NET_AMOUNT>
            <LIST_AMOUNT>135.80</LIST_AMOUNT>
            <LIST_RAISED>0</LIST_RAISED>
            <SURCHARGE_REBATE_LIST>
              <SURCHARGE_REBATE>
                <SURCHARGE_REBATE_CODE>1</SURCHARGE_REBATE_CODE>
                <SURCHARGE_REBATE_TEXT>Kupferzuschlag</SURCHARGE_REBATE_TEXT>
                <SURCHARGE_REBATE_AMOUNT>30.64</SURCHARGE_REBATE_AMOUNT>
              </SURCHARGE_REBATE>
            </SURCHARGE_REBATE_LIST>
          </PRICE_DATA>
        </ITEM>
        <ITEM>
          <RETURNCODE>I010</RETURNCODE>
          <RETURNCODE_TEXT>Preis und Verf&#252;gbarkeit korrekt ermittelt</RETURNCODE_TEXT>
          <ITEM_IDENT>
            <LINE_ITEM_NUMBER>2</LINE_ITEM_NUMBER>
            <MATERIAL_NUMBER>4711</MATERIAL_NUMBER>
            <REQUEST_QUANTITY>1</REQUEST_QUANTITY>
            <REQUEST_UNIT>PCE</REQUEST_UNIT>
          </ITEM_IDENT>
          <AVAILABILITY_DATA>
            <AVAILABILITY_STATUS>B</AVAILABILITY_STATUS>
            <AVAILABILITY_PARTNER_WAREHOUSE>22</AVAILABILITY_PARTNER_WAREHOUSE>
            <PARTNER_WAREHOUSE_NAME>Zentrallager</PARTNER_WAREHOUSE_NAME>
          </AVAILABILITY_DATA>
          <PRICE_DATA>
            <PRICE_AMOUNT>114526.00</PRICE_AMOUNT>
            <NET_AMOUNT>114526.00</NET_AMOUNT>
            <LIST_AMOUNT>122269.00</LIST_AMOUNT>
            <LIST_RAISED>0</LIST_RAISED>
          </PRICE_DATA>
        </ITEM>
        <ITEM>
          <RETURNCODE>E106</RETURNCODE>
          <RETURNCODE_TEXT>Artikel ist gel&#246;scht</RETURNCODE_TEXT>
          <ITEM_IDENT>
            <LINE_ITEM_NUMBER>3</LINE_ITEM_NUMBER>
            <MATERIAL_NUMBER>0100</MATERIAL_NUMBER>
            <REQUEST_QUANTITY>1</REQUEST_QUANTITY>
            <REQUEST_UNIT>PCE</REQUEST_UNIT>
          </ITEM_IDENT>
        </ITEM>
      </ITEM_LIST>
    </a:PRICE_AVAIL_RESPONSE>
  </soap:Body>
</soap:Envelope>
""".encode("ISO-8859-1")
