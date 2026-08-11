"""Minimal HTML fixtures for fega_schmitt_client.web tests.

These are trimmed-down reproductions of the real markup structure found
during the research documented in docs/extensions.md (sections 2.3-2.8),
not full page captures - only the parts each parser actually reads.
"""

SEARCH_RESULTS_HTML = """
<html><body>
<div data-id="121350"
     data-compare="121350;NEUT Gummischlauchleitung H07RN-F 5G16 TR500m schwarz;https://shop.fega.de/media/PIM-Media-Small/12/1213/12135/121350.jpg"
     class="fsProductList__item resizeTile ">
  <a href="https://shop.fega.de/product/Kabel-Leitungen--Gummischlauchleitung-H07RN-F-5G16-TR500m-schwarz---121350.html">
    <img src="https://shop.fega.de/media/PIM-Media-Small/12/1213/12135/121350.jpg" alt="">
  </a>
</div>
<a class="fsSucheWerbung__tile__item no-fade" href="https://shop.fega.de/community/portal.php?bold=&amp;cmd=detail/98993&amp;lid=104s&amp;artnr=121350">
  Werbekachel, kein data-compare
</a>
</body></html>
"""

ARTICLE_DETAIL_HTML = """
<html><body>
<div class="fsProductInfo__item">
  <span class="fsProductInfo__label">Warengruppe</span>
  <span class="fsProductInfo__text">
    <a class="fsLink fsLink--text" href="https://shop.fega.de/abtest/scripts/shop.php?bold=&amp;cmd=Hierarchie/UWG_1_1_0&amp;mode=list">
      Aderendh&uuml;lsen
    </a>
  </span>
</div>
<div class="fsProductInfo__item">
  <span class="fsProductInfo__label">Meine Artikelnummer</span>
  <div class="fsProductInfo__form">
    <input class="fsProductInfo__input" type="text" name="ownArticleNumber" data-orgarnr="051430" value="MY-OWN-NUMBER">
  </div>
</div>
<img class="width-100" src="https://shop.fega.de/media/PIM-Media-Big/example/pbm_051430.jpg.jpg" alt="">
<div data-variables="{&quot;oxom_arnr&quot;:&quot;051430&quot;,&quot;oxom_ean&quot;:&quot;4016705110575&quot;,&quot;supplierName&quot;:&quot;PROTEC.class&quot;,&quot;supplierItemNumber&quot;:&quot;05101057&quot;,&quot;supplierItemNumber3&quot;:&quot;PAEH 1000\\/12&quot;,&quot;supplierNumber&quot;:&quot;79559&quot;,&quot;variants&quot;:[{&quot;anz&quot;:&quot;2&quot;,&quot;arnrlist&quot;:&quot;054821,875999&quot;,&quot;values&quot;:{&quot;EF000007&quot;:{&quot;val1&quot;:&quot;EV000233&quot;}}},{&quot;anz&quot;:&quot;1&quot;,&quot;arnrlist&quot;:&quot;051870&quot;,&quot;values&quot;:{&quot;EF000007&quot;:{&quot;val1&quot;:&quot;EV000080&quot;}}}]}" class="fscomponent fsWebsite fsVarHolderInitializer fsOxomi">
</div>
<div class="fscomponent fsProductOverview">
  <div class="fsProductOverview__item ">
    <div class="fsProductOverview__label alternativesCheckboxContainer hidden"></div>
    <span class="fsProductOverview__label alternativesLabelContainer">Farbe:</span>
    <div class="fsProductOverview__value">
      rot						</div>
  </div>
  <div class="fsProductOverview__item ">
    <div class="fsProductOverview__label alternativesCheckboxContainer hidden"></div>
    <span class="fsProductOverview__label alternativesLabelContainer">Werkstoff:</span>
    <div class="fsProductOverview__value">
      Kupfer						</div>
  </div>
</div>
<h2 class="fsProductTeaser__headline">Zubehör</h2>
<button class="fsBtn fsBtn--outline d-none d-sm-flex fscomponent fsWand" data-compare="051430,051988,057288,053943" data-category="Zubeh&ouml;r" data-wand="https://shop.fega.de/abtest/scripts/shop.php?bold=&amp;cmd=Wand&amp;pas=VGLAD|051430,051988,057288,053943||DetailDektop">
    Jetzt vergleichen
</button>
<h2 class="fsProductTeaser__headline">Oft zusammengekauft mit</h2>
<button class="fsBtn fsBtn--outline d-none d-sm-flex fscomponent fsWand" data-compare="051430,051431,051432">
    Jetzt vergleichen
</button>
<h2 class="fsProductTeaser__headline">Varianten</h2>
<button class="fsBtn fsBtn--outline d-none d-sm-flex fscomponent fsWand" data-compare="051430,054821,051870,051871">
    Jetzt vergleichen
</button>
<h2 class="fsProductTeaser__headline">Alternativen</h2>
<button class="fsBtn fsBtn--outline d-none d-sm-flex fscomponent fsWand" data-compare="051430,6169773,9641674">
    Jetzt vergleichen
</button>
</body></html>
"""

ARTICLE_DETAIL_NO_ALTERNATIVES_HTML = """
<html><body>
<div data-variables="{&quot;oxom_arnr&quot;:&quot;253439&quot;}" class="fscomponent fsWebsite fsVarHolderInitializer fsOxomi">
</div>
<h2 class="fsProductTeaser__headline">Zubehör</h2>
<button class="fsBtn fsBtn--outline d-none d-sm-flex fscomponent fsWand" data-compare="253439,030810,030809">
    Jetzt vergleichen
</button>
<h2 class="fsProductTeaser__headline">Varianten</h2>
</body></html>
"""

# No data-variables JSON blob at all (e.g. an older cached snapshot) -
# exercises parse_article_variants()'s fallback to the teaser section.
ARTICLE_DETAIL_NO_DATA_VARIABLES_HTML = """
<html><body>
<h2 class="fsProductTeaser__headline">Varianten</h2>
<button class="fsBtn fsBtn--outline d-none d-sm-flex fscomponent fsWand" data-compare="051430,054821,051870">
    Jetzt vergleichen
</button>
</body></html>
"""

CART_HTML = """
<html><body>
<button class="fsDropdown__item fscomponent fsDeleteCurrentWk" data-wkname="Testkorb" type="button"></button>
<form data-action="https://shop.fega.de/abtest/scripts/shop.php?bold=&amp;cmd=BasketView/13586483&amp;mode=changeName"></form>
<select class="fsForm__select" name="sel_wk">
  <option value="12335021">Projekt A</option>
  <option value="12273523">Projekt B</option>
</select>
<input type="hidden" name="pwahl_id_0" value="59298595">
<input type="hidden" name="pro_id_0" value="518927">
<input type="hidden" name="user_info_0" value="Testkommentar">
<input class="fsForm__input fsWkAnzNumberField" type="text" data-id="0" old_menge="20" name="pro_anz_0" data-menge value="20">
</body></html>
"""

ORDER_LIST_HTML = """
<html><body>
<tr class="auftr_tr fscomponent fsAuftragRow scroll-mt" data-id="45238958_1" id="45238958_1">
  <td class="ainr_td" data-sort-value="45238958" data-sort-ident="2"><span>45238958/1</span></td>
  <td class="d-none d-md-table-cell" data-sort-value="14.01.26" data-sort-ident="3"><span>14.01.26</span></td>
  <td><span>Rechnung erstellt</span></td>
  <td><span class="fscomponent fsTooltip tooltipNoClick fsTourList overviewSvg">x</span></td>
</tr>
<tr class="hiddenIp auftrag_additional" data-id="45238958_1">
  <td colspan="9">expandable detail row, should not be double-counted</td>
</tr>
"""

ORDER_DETAIL_HTML = """
<html><body>
<tr class="fsAuftraegeDetail__container__content__product">
  <td class="position-relative">
    <span class="fsBadge fsBadge--blue20 position-absolute top-0 start-0 m-2">405881</span>
    <span class="position-absolute bottom-0 start-0 m-3">4.</span>
  </td>
  <td><a href="https://shop.fega.de/product/Wago--foo---405881.html"><b class="black">WAGO 3 Leiter Schutzleiterklemme 2016-1307</b></a></td>
  <td><span class="availability-badge availability-badge--green"></span><span class="green">20</span></td>
  <td>20</td>
  <td>0</td>
</tr>
"""

DEAL_CAMPAIGNS_HTML = """
<html><body>
<div class="fsDeal__row__container__item--breit fscomponent fsDealKachel fsTooltip" data-id="27923">
  <div class="upper"><img src="https://shop.fega.de/downloads/deal/2/example.jpg" alt="">
    <div class="right"><img src="https://shop.fega.de/downloads/deal/2/logo.png" alt="">
      <div class="text"><h3>AKTIONSPREISE SICHERN</h3><h4>Sonderabverkauf Licht</h4></div>
    </div>
  </div>
</div>
<div class="fsDeal__row__container__item--breit fscomponent fsDealKachel fsTooltip" data-id="31483">
  <div class="upper"><img src="https://shop.fega.de/downloads/deal/1/bg.png" alt="">
    <div class="right"><img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACg==" alt="">
      <div class="text"><h3></h3><h4>Standardtypen von Makita</h4></div>
    </div>
  </div>
</div>
</body></html>
"""

# Trimmed reproduction of cmd=AjaxKLaeng/<matnr> (extensions.md 2.10) - two
# locations, to verify rows are scoped to the location header they follow
# rather than parsed globally. Includes both a "zum Ablängen" remainder row
# (no fixed length) and a "fest" row with a fixed drum length, matching the
# two row shapes seen on the real page.
CABLE_LENGTHS_HTML = """
<div class="fsKlaeng">
  <div class="col-xs-12 text-center bold height lg bg-blue20">
    Bestand Zentrallager
  </div>
  <div class="row fsKlaeng__availList">
    <div class="hide-mobile">
      <div class="col-xs-12 border-bottom">
        <div class="row">
          <div class="col-sm-3 height lg height-auto">
            KTG Trommel						</div>
          <div class="col-sm-2 height lg height-auto">
            zum Ablängen 						</div>
          <div id="kap_1_0" class="col-sm-2 height lg height-auto">

          </div>
          <div class="col-sm-2 height lg height-auto text-center">
            1						</div>
          <div class="col-sm-3 height lg height-auto text-right">
            34						</div>
        </div>
      </div>
      <div class="col-xs-12 border-bottom">
        <div class="row">
          <div class="col-sm-3 height lg height-auto">
            Einwegtrommel						</div>
          <div class="col-sm-2 height lg height-auto">
            fest 						</div>
          <div id="kap_1_1" class="col-sm-2 height lg height-auto">
            500
          </div>
          <div class="col-sm-2 height lg height-auto text-center">
            35						</div>
          <div class="col-sm-3 height lg height-auto text-right">
            17500						</div>
        </div>
      </div>
    </div>
  </div>
  <div class="col-xs-12 text-center bold height lg bg-blue20">
    Bestand FEGA &amp; Schmitt Erlangen
  </div>
  <div class="row fsKlaeng__availList">
    <div class="hide-mobile">
      <div class="col-xs-12 border-bottom">
        <div class="row">
          <div class="col-sm-3 height lg height-auto">
            KTG Trommel						</div>
          <div class="col-sm-2 height lg height-auto">
            zum Ablängen 						</div>
          <div id="kap_1_2" class="col-sm-2 height lg height-auto">

          </div>
          <div class="col-sm-2 height lg height-auto text-center">
            2						</div>
          <div class="col-sm-3 height lg height-auto text-right">
            80						</div>
        </div>
      </div>
    </div>
  </div>
</div>
"""

ARTICLE_DETAIL_WITH_CUTTING_FEE_HTML = """
<html><body>
<div data-variables="{&quot;oxom_arnr&quot;:&quot;104260&quot;}" class="fscomponent fsWebsite fsVarHolderInitializer fsOxomi">
</div>
<p class="mt-4">
    Eventuell fallen  Schnittkosten in Höhe von <span class="bold">9,95 €</span> an.							</p>
</body></html>
"""

LOGIN_SUCCESS_HEADERS = {"Location": "https://shop.fega.de/scripts/shop.php?cmd=Startseite"}
LOGIN_FAILURE_HEADERS = {"Location": "https://shop.fega.de/abtest?warnings=Bitte+melden+Sie+sich+neu+an.&gg=Startseite"}
