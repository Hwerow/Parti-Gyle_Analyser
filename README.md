# Parti-Gyle Analyser 1.9

A Python tool for brewers to analyse historical Parti-Gyle brewing records and converts them into scaled Single Gyle recipes (e.g., 24 L homebrew batches) compatible with modern brewing software like Brewfather.

## Features
- **Parti-Gyle Analysis:** Calculates Mass Balance, Pre-Boil SG, and Extract for multiple coppers (supports 2 or 3 copper setups).
- **Advanced Calculations:** Uses the **Tinseth Formula** for IBU and **Morey Equation** for Color (EBC/SRM).
- **Single Gyle Conversion:** Intelligently apportions ingredients from a complex multi-gyle blend into a single scaled recipe.
- **Smart Scaling:** - Adjusts for system efficiency (e.g., scaling Industrial ~90% -> Homebrew 75%).
  - Adjusts hop weights based on form (Whole vs. Pellet) and boil time changes.
- **Detailed Reporting:** Outputs a comprehensive text report, a JSON file, and a BeerXML recipe file suitable for import.

## Prerequisites
- **Windows 10/11**
- **Python 3.x** installed (Ensure "Add Python to PATH" is checked during installation).

## Installation
1. Download this repository (Code -> Download ZIP) or clone it:
   ```bash

   git clone [https://github.com/YOUR_USERNAME/Parti-Gyle-Analyser.git](https://github.com/YOUR_USERNAME/Parti-Gyle-Analyser.git)
## How to Use
See the Tritun Books YouTube Channel for a more detailed explanation.

Prepare your Data: Create a JSON file describing your Parti-Gyle brew (see examples/ folder).

Run the Tool: Double-click run_analysis.bat.

Select Input: A file dialog will appear. Select your JSON file.

Select Target: If multiple beers are defined (e.g., PA1, PA2), select the one you want to brew from the popup list.

Save Output: Choose a folder to save your results. You will be prompted for a filename [BeerName]. 
The tool will generate:

- [BeerName].txt: A human-readable report of the chemistry and blending, and a recipe.

- [BeerName].json: A JSON version of the recipe file.
  
- BeerXML Export: Automatically generates a standard [BeerName].xml file for direct import into Brewfather, Beersmith, and Grainfather.
Ready for editing to suit your system. [Note Only tested with Brewfather]


   




