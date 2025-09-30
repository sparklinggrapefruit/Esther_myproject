#Setting up the environment
pip install pandas openai matplotlib tkinter

import pandas as pd
from tkinter import filedialog, Tk

def upload_file():
    root = Tk()
    root.withdraw()  
    file_path = filedialog.askopenfilename(title="Select a file", filetypes=(("Text files", "*.txt"),))
    if file_path:
        # Assuming each article is separated by a new line and each field by a comma.
        df = pd.read_csv(file_path, delimiter=',', names=['Title', 'Authors', 'Abstract', 'Year', 'DOI'])
        print(df.head())  # For debugging: shows first few rows
        return df
    else:
        print("No file selected.")
        return None

# Testing file upload
if __name__ == "__main__":
    articles_df = upload_file()

import re
import pandas as pd

def parse_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = file.read()

    # Regular expressions to match each field
    authors_pattern = r"%A (.*?)\n"
    title_pattern = r"%T (.*?)\n"
    abstract_pattern = r"%X (.*?)\n"
    year_pattern = r"%D (.*?)\n"
    doi_pattern = r"%R (.*?)\n"

    # Find all matches
    authors = re.findall(authors_pattern, data)
    titles = re.findall(title_pattern, data)
    abstracts = re.findall(abstract_pattern, data)
    years = re.findall(year_pattern, data)
    dois = re.findall(doi_pattern, data)

    # Organize the data into a dictionary
    parsed_data = {
        "Authors": ["; ".join(authors[i:i+1]) for i in range(0, len(authors))],  # Combine authors for each article
        "Title": titles,
        "Abstract": abstracts,
        "Year Published": years,
        "DOI": dois
    }

    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(parsed_data)
    
    return df

# Test the function
file_path = "/mnt/data/exportlist.txt"
articles_df = parse_file(file_path)
print(articles_df.head())