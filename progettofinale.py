import streamlit as st
import pandas as pd
import json
from bs4 import BeautifulSoup
import fitz
import re
from concurrent.futures import ThreadPoolExecutor
import requests
from itertools import chain
from difflib import SequenceMatcher

# Cache the data fetching
@st.cache_data(show_spinner=False)
def load_json_data(json_path):
    with open(json_path, 'r') as file:
        data = json.load(file)
    return data

@st.cache_data(show_spinner=False)
def get_pdf_link(ingredient_id):
    # This function remains the same since it's not fetching data
    url = f"https://cir-reports.cir-safety.org/cir-ingredient-status-report/?id={ingredient_id}"
    response = requests.get(url).text
    soup = BeautifulSoup(response, "lxml")
    tab = soup.find("table")
    attach = tab.find("a")
    pidieffe = attach["href"]
    linktr = str(pidieffe).replace("../", "")
    pdf_link = "https://cir-reports.cir-safety.org/" + linktr
    return pdf_link

def extract_text_from_pdf_url(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            pdf_data = response.content
            text_pages = []
            document = fitz.open(stream=pdf_data, filetype="pdf")
            for page_num in range(len(document)):
                try:
                    page = document.load_page(page_num)
                    page_text = page.get_text()
                    if page_text:
                        text_pages.append((page_text, page_num + 1))
                    else:
                        st.warning(f"Nessun testo trovato nella pagina {page_num + 1}")
                except Exception as e:
                    st.error(f"Errore durante l'estrazione del testo dalla pagina {page_num + 1}: {str(e)}")
            return text_pages
        else:
            st.error(f"Errore durante l'apertura del PDF. Codice di stato: {response.status_code}")
    except Exception as e:
        st.error(f"Errore generale durante l'operazione di estrazione del testo dal PDF: {str(e)}")

def extract_noael_and_ld50(text_pages):
    noael_pattern = re.compile(r'(.*?NOAEL.*?\d+\.?\d*\s*[a-zA-Z/]+.*?(\.|$))', re.IGNORECASE)
    ld50_pattern = re.compile(r'(.*?LD50.*?\d+\.?\d*\s*[a-zA-Z/]+.*?(\.|$))', re.IGNORECASE)
    
    noael_matches = []
    ld50_matches = []
    
    for text, page_num in text_pages:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if re.search(noael_pattern, line):
                previous_line = lines[i - 1] if i > 0 else ""
                formatted_match = highlight_numbers(f"{previous_line}\n{line}")
                noael_matches.append((formatted_match, page_num))
            if re.search(ld50_pattern, line):
                previous_line = lines[i - 1] if i > 0 else ""
                formatted_match = highlight_numbers(f"{previous_line}\n{line}")
                ld50_matches.append((formatted_match, page_num))
    
    return noael_matches, ld50_matches

def echanoael(zuppa):
    noael_matches = []
    div = zuppa.find('div', id='SectionContent')
    dl = div.find_all('dl')

    for sez in dl:
        coldx = sez.find_all('dd')
        for ddtag in coldx:
            if ddtag.text == "NOAEL":
                h3 = ddtag.find_previous('h3')
                nxt = ddtag.find_next('dd')
                risp = f"Il NOAEL con queste condizioni:  {h3.text} è  {nxt.text}"
                noael_matches.append(risp)
    
    return noael_matches

def echadnel(zuppa):
    dnel_matches = []
    div = zuppa.find('div', id='SectionContent')
    dl = div.find_all('dl')

    for sez in dl:
        coldx = sez.find_all('dd')
        for ddtag in coldx:
            if ddtag.text == "DNEL (Derived No Effect Level)":
                h3 = ddtag.find_previous('h3')
                nxt = ddtag.find_next('dd')
                risp = f"Il DNEL con queste condizioni:  {h3.text} è  {nxt.text}"
                dnel_matches.append(risp)
    
    return dnel_matches

def highlight_numbers(text):
    text = re.sub(r'(\d+,\d+\.?\d*)', r'<b style="color:red;">\1</b>', text)
    
    highlight_words = ["rat", "NOAEL", "LD50", "rats", "rabbits", "ld50", "g/kg", "mg/kg/day", "mg/kg"]
    if highlight_words:
        pattern = r'\b(' + '|'.join(re.escape(word) for word in highlight_words) + r')\b'
        text = re.sub(pattern, r'<span style="color:yellow">\1</span>', text)
    
    return text

def find_keys_with_word(js, word):
    keys = []
    
    if isinstance(js, dict):
        for key, value in js.items():
            if word in key:
                keys.append(key)
            keys.extend(find_keys_with_word(value, word))
    elif isinstance(js, list):
        for item in js:
            keys.extend(find_keys_with_word(item, word))
    
    return keys

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def get_max_similarity(ingredient, json_keys):
    return max(similar(ingredient, key) for key in json_keys)

def display_echa_results(noael_matches, dnel_matches):
    if noael_matches:
        with st.expander("Mostra tabella NOAEL (ECHA)", expanded=False):
            st.write("### Valori NOAEL trovati:")
            noael_df = pd.DataFrame(noael_matches, columns=["NOAEL value"])
            st.write(noael_df.to_html(escape=False, index=False), unsafe_allow_html=True)

    if dnel_matches:
        with st.expander("Mostra tabella DNEL (ECHA)", expanded=False):
            st.write("### Valori dnel trovati:")
            dnel_df = pd.DataFrame(dnel_matches, columns=["DNEL value"])
            st.write(dnel_df.to_html(escape=False, index=False), unsafe_allow_html=True)

    if not noael_matches and not dnel_matches:
        st.write("Nessun valore NOAEL o LD50 trovato per ECHA.")

def ldpub(jsondata):
    result = []
    for section in jsondata["Record"]["Section"]:
        if "Section" in section:
            for subsection in section["Section"]:
                for info in subsection["Information"]:
                    if "Value" in info and "StringWithMarkup" in info["Value"]:
                        for item in info["Value"]["StringWithMarkup"]:
                            if item["String"].startswith("LD50"):
                                result.append(item["String"])
    return result

def display_ld_results(l_matches):
    if l_matches:
        with st.expander("Mostra tabella LD50 (PubChem)", expanded=False):
            st.write("### Valori LD50 trovati:")
            l_df = pd.DataFrame(l_matches, columns=["LD50 value"])
            st.write(l_df.to_html(escape=False, index=False), unsafe_allow_html=True)

    if not l_matches:
        st.write("Nessun valore LD50 trovato per PubChem.")
 
def main():
    st.set_page_config(page_title="Toxicity Program", layout="wide")
    
    st.title("Toxic report ")
    st.markdown("Benvenuto. Seleziona un ingrediente per avere le informazioni sulla sua tossicità.")
    
    st.write("### Caricamento dati...")

    # Load the JSON file directly from the directory
    json_path = "cirjs.json"
    data = load_json_data(json_path)
    json_epath = "invecchia.json"
    echa = load_json_data(json_epath)
    json_ppath = "pubchem.json"
    pub = load_json_data(json_ppath)
    st.write("Dati caricati con successo!")
    
    ingredient = st.selectbox("Scrivi il nome dell'ingrediente", [""] + list(data.keys()), index=0)
    
    if ingredient:
        ingredient_id = data.get(ingredient)
        
        if ingredient_id:
            pdf_link = get_pdf_link(ingredient_id)
            
            st.write(f"Link al PDF: [Clicca qui per visualizzare il PDF]({pdf_link})")
            
            if st.button("Estrai Noael / Ld50"):
                with st.spinner('Estrazione del testo in corso...potrebbe richiedere alcuni secondi'):
                    try:
                        text_pages = extract_text_from_pdf_url(pdf_link)
                        
                        noael_matches, ld50_matches = extract_noael_and_ld50(text_pages)
                        
                        if noael_matches:
                            with st.expander("Mostra tabella NOAEL", expanded=False):
                                st.write("### Valori NOAEL trovati:")
                                noael_df = pd.DataFrame(noael_matches, columns=["NOAEL value", "Page"])
                                st.write(noael_df.to_html(escape=False, index=False), unsafe_allow_html=True)
                        
                        if ld50_matches:
                            with st.expander("Mostra tabella LD50", expanded=False):
                                st.write("### Valori LD50 trovati:")
                                ld50_df = pd.DataFrame(ld50_matches, columns=["LD50 value", "Page"])
                                st.write(ld50_df.to_html(escape=False, index=False), unsafe_allow_html=True)
                        
                        if not noael_matches and not ld50_matches:
                            st.write("Nessun valore NOAEL o LD50 trovato.")                            
                        
                    except Exception as e:
                        st.error(f"ERRORE: {e}")
        else:
            st.warning("Ingrediente non trovato.")
    
        cleani = re.sub(r'[^\w\s]', '', ingredient)
        words = cleani.split()
        ecing = []
        for word in words:
            w = find_keys_with_word(echa, word)
            ecing.append(w)
            wl = find_keys_with_word(echa, word.lower())
            ecing.append(wl)
        fl = list(chain(*ecing))
        sfl = set(fl)       
        sorted_ingredients = sorted(sfl, key=lambda x: get_max_similarity(ingredient, [x]), reverse=True)
        st.write("")
        st.write("Ingredienti echa contenenti parte del nome ricercato sopra")
        ingecha = st.selectbox("Ing Echa", [""] + list(sorted_ingredients), index=0) 
        if ingecha:
            urlecha = echa.get(ingecha)
            if urlecha:
                echalink = "https://echa.europa.eu/it/registration-dossier/-/registered-dossier/"+str(urlecha)+"/7/1"
                st.write(f"Link al dossier Echa: [Clicca qui per visualizzare il dossier]({echalink})")
                if st.button("Estrai valori Echa"):
                    response = requests.get(echalink)
                    soup = BeautifulSoup(response.content, 'html.parser')
                    dl = echadnel(soup)
                    nl = echanoael(soup)

                    noael_matches = [(highlight_numbers(noael),) for noael in nl]
                    dnel_matches = [(highlight_numbers(dnel),) for dnel in dl]
                    display_echa_results(noael_matches, dnel_matches)

        pubing = []
        for word in words:
            w = find_keys_with_word(pub, word)
            pubing.append(w)
            wl = find_keys_with_word(pub, word.lower())
            pubing.append(wl)
            wu = find_keys_with_word(pub, word.upper())
            pubing.append(wu)
        fl = list(chain(*pubing))
        sfl = set(fl)       
        sorted_ingredients = sorted(sfl, key=lambda x: get_max_similarity(ingredient, [x.lower()]), reverse=True)
        st.write("")
        st.write("Ingredienti pubchem contenenti parte del nome ricercato sopra")
        ingpub = st.selectbox("Ing Pub", [""] + list(sorted_ingredients), index=0)
        if ingpub:
            urlpub = pub.get(ingpub)
            if urlpub:
                publink = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/annotation/"+str(urlpub)+"/JSON/?toc=Hazardous%20Substances%20Data%20Bank%20(HSDB)+TOC&heading=Non+Human+Toxicity+Values+(Complete)"
                st.write(f"Link al dossier PubChem: [Clicca qui per visualizzare il dossier]({publink})")
                if st.button("Estrai valori PubChem"):
                    txt = requests.get(publink).text
                    pubj = json.loads(txt)
                    ris = ldpub(pubj)
                    l_matches = [(highlight_numbers(ld),) for ld in ris]
                    display_ld_results(l_matches)

if __name__ == "__main__":
    main()
