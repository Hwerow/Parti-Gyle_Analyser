# Parti-Gyle Analyser 1.7

A Python tool for brewers to analyse historical Parti-Gyle brewing records and convert them into scaled Single Gyle recipes (e.g., 24L homebrew batches) compatible with modern brewing software like Brewfather.

## Features
- **Parti-Gyle Analysis:** Calculates Mass Balance, Pre-Boil SG, and Extract for multiple coppers (supports 2 or 3 copper setups).
- **Advanced Calculations:** Uses the **Tinseth Formula** for IBU and **Morey Equation** for Color (EBC/SRM).
- **Single Gyle Conversion:** Intelligently apportions ingredients from a complex multi-gyle blend into a single scaled recipe.
- **Smart Scaling:** - Adjusts for system efficiency (e.g., scaling Industrial ~90% -> Homebrew 75%).
  - Adjusts hop weights based on form (Whole vs. Pellet) and boil time changes.
- **Detailed Reporting:** Outputs a comprehensive text report, a JSON file, and a BeerXML recipe file.

## Prerequisites
- **Windows 10/11**
- **Python 3.x** installed (Ensure "Add Python to PATH" is checked during installation).

## Installation
1. Download this repository (Code -> Download ZIP) or clone it:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/Parti-Gyle-Analyser.git](https://github.com/YOUR_USERNAME/Parti-Gyle-Analyser.git)