import json
import math
import os
import sys
import tkinter as tk
import xml.etree.ElementTree as ET
from xml.dom import minidom
from tkinter import filedialog, messagebox, simpledialog

# --- PG_Analyser_1.9 ---

# --- Constants ---
BRL_TO_L = 163.66
LB_TO_KG = 0.453592
IMP_GAL_PER_BRL = 36.0     
US_GAL_PER_BRL = 43.23     

# --- Helper Functions ---
def sg_to_points(sg):
    return (sg - 1.0) * 1000

def points_to_sg(points):
    return 1.0 + (points / 1000)

def format_weight(kg):
    if kg < 1.0:
        return f"{kg*1000:.1f}g"
    return f"{kg:.3f}kg"

def ebc_to_lovibond(ebc):
    return ebc / 1.97

def calculate_morey_ebc(total_mcu_lov_lb, volume_us_gal):
    if volume_us_gal <= 0: return 0.0
    mcu = total_mcu_lov_lb / volume_us_gal
    srm = 1.4922 * (mcu ** 0.6859)
    return srm * 1.97

def calculate_tinseth_ibu(alpha, weight_lb, time_min, volume_brl, boil_sg, kettle_util_factor, relative_util=1.0):
    if volume_brl <= 0: return 0.0
    vol_gal = volume_brl * IMP_GAL_PER_BRL 
    weight_oz = weight_lb * 16
    concentration = (alpha * weight_oz * 74.9) / vol_gal
    bigness = 1.65 * (0.000125 ** (boil_sg - 1))
    boil_time_factor = (1 - math.exp(-0.04 * time_min)) / 4.15
    utilization = bigness * boil_time_factor * relative_util
    return utilization * concentration * kettle_util_factor

class BeerSelectionDialog(simpledialog.Dialog):
    def __init__(self, parent, beers):
        self.beers = beers
        self.selected_beer = None
        super().__init__(parent, title="Select Target Beer")

    def body(self, master):
        tk.Label(master, text="Select which beer to convert:").pack(pady=5)
        self.listbox = tk.Listbox(master, height=len(self.beers), selectmode=tk.SINGLE)
        for b in self.beers:
            self.listbox.insert(tk.END, b)
        self.listbox.pack(padx=10, pady=5)
        self.listbox.select_set(0) 
        return self.listbox

    def apply(self):
        try:
            index = self.listbox.curselection()[0]
            self.selected_beer = self.beers[index]
        except IndexError:
            self.selected_beer = self.beers[0]

class PartiGyleAnalyzer:
    def __init__(self, data, target_beer_override=None):
        self.data = data
        self.copper_stats = {}
        self.total_wort_pts_system = 0
        self.total_grain_mcu_lov = 0 
        self.blend_results = []
        self.single_gyle_recipe = {}
        self.report_lines = []
        
        self.settings = data.get('single_gyle_settings', {
            "target_beer": "PA2",
            "batch_size_litres": 24.0,
            "target_efficiency_percent": 75.0,
            "revised_boil_time_minutes": 70,
            "hop_conversion": {"target_form": "pellet", "weight_adjustment_factor": 0.90}
        })
        
        if "boil_size_litres" not in self.settings:
            self.settings["boil_size_litres"] = self.settings["batch_size_litres"] * 1.15

        if target_beer_override:
            self.settings['target_beer'] = target_beer_override

    def run_analysis(self):
        self._calculate_mass_balance()
        self._calculate_ibu_ebc()
        self._calculate_blending()
        self._convert_to_single_gyle()

    def _calculate_mass_balance(self):
        self.report_lines.append("--- Mass Balance & Pre-Boil Analysis ---")
        total_grain_potential_pts_gal = 0
        self.total_grain_mcu_lov = 0
        for g in self.data['mash_phase']['grains']:
            ppg = sg_to_points(g['potential_sg'])
            total_grain_potential_pts_gal += g['weight_lb'] * ppg
            lov = ebc_to_lovibond(g['color_ebc'])
            self.total_grain_mcu_lov += g['weight_lb'] * lov

        self.copper_stats = {}
        for copper in self.data['boil_phase']:
            k_id = copper['kettle_id']
            vol_brl = copper['post_boil_volume_brl']
            avail_brl = copper.get('volume_available_for_blending_brl', vol_brl)
            measured_sg = copper['measured_sg']
            
            total_pts_gal = vol_brl * IMP_GAL_PER_BRL * sg_to_points(measured_sg)
            adjunct_pts_gal = 0
            adjunct_mcu_lov = 0
            for adj in copper['adjuncts']:
                ppg = sg_to_points(adj['potential_sg'])
                adjunct_pts_gal += adj['weight_lb'] * ppg
                lov = ebc_to_lovibond(adj['color_ebc'])
                adjunct_mcu_lov += adj['weight_lb'] * lov
            wort_pts_gal = total_pts_gal - adjunct_pts_gal
            
            input_vol = 0
            for r in self.data['runnings_actuals']:
                if r['dest_kettle'] == k_id:
                    input_vol = r['measured_input_vol_brl']
                    break
            
            pre_boil_sg = 1.000
            if input_vol > 0:
                pre_boil_sg = points_to_sg(wort_pts_gal / (input_vol * IMP_GAL_PER_BRL))
            
            self.copper_stats[k_id] = {
                "pre_boil_sg": pre_boil_sg,
                "wort_pts_gal": wort_pts_gal,
                "adjunct_pts_gal": adjunct_pts_gal,
                "adjunct_mcu_lov": adjunct_mcu_lov, 
                "post_vol_brl": vol_brl,
                "avail_vol_brl": avail_brl,
                "measured_sg": measured_sg,
                "util_factor": copper.get('utilization_factor', 1.0),
                "total_ibu": 0,
                "ebc": 0,
                "total_mcu_lov": 0
            }
            self.report_lines.append(f"{copper['description']} ({k_id}):")
            self.report_lines.append(f"  Pre-Boil SG Est: {pre_boil_sg:.3f}")
            self.report_lines.append(f"  Wort Extract from Grain: {int(wort_pts_gal)} gal-pts")

        self.total_wort_pts_system = sum(c['wort_pts_gal'] for c in self.copper_stats.values())
        self.report_lines.append("")

    def _calculate_ibu_ebc(self):
        self.report_lines.append("--- Advanced IBU & EBC Calculation (Parti-Gyle) ---")
        for copper in self.data['boil_phase']:
            k_id = copper['kettle_id']
            stats = self.copper_stats[k_id]
            self.report_lines.append(f"Analysis for {copper['description']}:")
            
            total_ibu = 0
            for hop in copper['hops_whole']:
                ibu = calculate_tinseth_ibu(hop['alpha'], hop['weight_lb'], hop['time_min'], 
                                            stats['post_vol_brl'], stats['measured_sg'], stats['util_factor'])
                total_ibu += ibu
                self.report_lines.append(f"  Boil Hop ({hop['name']}): {ibu:.1f} IBU")
            
            steps = copper.get('post_boil_steps', [])
            if not steps and 'post_boil_stand' in copper and copper['post_boil_stand'].get('active'):
                 s = copper['post_boil_stand']
                 steps = [{'step_type': 'stand', 'hops': s.get('add_whole_hops', []), 
                           'duration_min': s.get('duration_min', 30), 
                           'utilization_factor_relative': 0.1,
                           'temperature_c': s.get('avg_temp_c', 80)}] 

            for step in steps:
                if step['step_type'] == 'stand':
                    u = step.get('utilization_factor_relative', 0.1)
                    for hop in step.get('hops', []):
                        ibu = calculate_tinseth_ibu(hop['alpha'], hop['weight_lb'], step['duration_min'],
                                                    stats['post_vol_brl'], stats['measured_sg'], stats['util_factor'], u)
                        total_ibu += ibu
                        self.report_lines.append(f"  Stand Hop ({hop['name']}): {ibu:.1f} IBU")
            
            stats['total_ibu'] = total_ibu
            
            if self.total_wort_pts_system > 0:
                grain_mcu_share = (stats['wort_pts_gal'] / self.total_wort_pts_system) * self.total_grain_mcu_lov
            else:
                grain_mcu_share = 0
            total_mcu_lov = grain_mcu_share + stats['adjunct_mcu_lov']
            stats['total_mcu_lov'] = total_mcu_lov
            
            vol_us_gal = stats['post_vol_brl'] * US_GAL_PER_BRL
            stats['ebc'] = calculate_morey_ebc(total_mcu_lov, vol_us_gal)
            
            self.report_lines.append(f"  >> Total IBU: {total_ibu:.1f}")
            self.report_lines.append(f"  >> Estimated EBC (Morey): {stats['ebc']:.1f}")
            self.report_lines.append("")

    def _calculate_blending(self):
        self.report_lines.append("--- Blending Analysis & Composition ---")
        for beer in self.data['blending_matrix']['final_beers']:
            self.report_lines.append(f"Beer: {beer['name']}")
            self.report_lines.append(f"  {'Source':<12} {'Vol (brl)':<10} {'SG':<8} {'% Vol':<8}")
            self.report_lines.append("  " + "-"*40)
            comps = beer['components']
            total_vol = sum(comps.values())
            
            if total_vol <= 0:
                self.report_lines.append(f"  {beer['name']} has 0 volume. Skipping.")
                continue

            og_pts_sum = 0
            total_ibu_mass = 0
            total_mcu_sum = 0
            for k_id in ['copper_1', 'copper_2', 'copper_3']:
                vol_used = comps.get(k_id, 0)
                if vol_used > 0:
                    stats = self.copper_stats[k_id]
                    pct = (vol_used / total_vol) * 100
                    og_pts_sum += vol_used * sg_to_points(stats['measured_sg'])
                    total_ibu_mass += vol_used * stats['total_ibu']
                    
                    if stats['post_vol_brl'] > 0:
                        fraction_used = vol_used / stats['post_vol_brl']
                    else:
                        fraction_used = 0
                        
                    total_mcu_sum += stats['total_mcu_lov'] * fraction_used
                    self.report_lines.append(f"  {k_id:<12} {vol_used:<10.1f} {stats['measured_sg']:<8.3f} {pct:<8.1f}")
            
            liq_vol = comps.get('liquor', 0)
            if liq_vol > 0:
                pct = (liq_vol / total_vol) * 100
                self.report_lines.append(f"  {'liquor':<12} {liq_vol:<10.1f} {'1.000':<8} {pct:<8.1f}")
            
            final_og = points_to_sg(og_pts_sum / total_vol)
            final_ibu = total_ibu_mass / total_vol
            final_abv = (final_og - 1.010) * 131.25
            final_vol_us_gal = total_vol * US_GAL_PER_BRL
            final_ebc = calculate_morey_ebc(total_mcu_sum, final_vol_us_gal)
            target_og = beer.get('target_og', 0)
            og_var = final_og - target_og
            
            self.blend_results.append({
                "name": beer['name'],
                "vol_brl": total_vol,
                "og": final_og,
                "target_og": target_og,
                "ibu": final_ibu,
                "ebc": final_ebc,
                "abv": final_abv,
                "components": comps
            })
            self.report_lines.append("  " + "-"*40)
            self.report_lines.append(f"  TOTALS:      {total_vol:<10.1f} {final_og:<8.3f}")
            self.report_lines.append(f"  STATS:       IBU: {final_ibu:.1f} | EBC: {final_ebc:.1f} | ABV: {final_abv:.1f}%")
            self.report_lines.append(f"  VARIANCES:   OG: {og_var:+.3f} (Target {target_og:.3f})")
            self.report_lines.append("")

    def _convert_to_single_gyle(self):
        target_beer = self.settings['target_beer']
        target_vol_l = self.settings['batch_size_litres']
        target_boil_size_l = self.settings['boil_size_litres']
        target_efficiency = self.settings['target_efficiency_percent']
        revised_boil_mins = self.settings['revised_boil_time_minutes']
        hop_config = self.settings.get('hop_conversion', {})
        target_hop_form = hop_config.get('target_form', 'whole')
        hop_weight_factor = hop_config.get('weight_adjustment_factor', 1.0)

        self.report_lines.append(f"--- Single Gyle Conversion: {target_beer} ---")
        self.report_lines.append(f"Settings: {target_vol_l}L Batch | {target_boil_size_l}L Boil | {target_efficiency}% Eff | {revised_boil_mins} min")
        self.report_lines.append(f"Hops: Form '{target_hop_form}' | Adjustment Factor: {hop_weight_factor}")
        self.report_lines.append("")
        
        beer_data = next((b for b in self.blend_results if b['name'] == target_beer), None)
        if not beer_data:
            self.report_lines.append(f"Error: Beer '{target_beer}' not found in blending matrix.")
            return

        target_og = beer_data['og']
        
        ratios = {}
        for k_id in ['copper_1', 'copper_2', 'copper_3']:
            used = beer_data['components'].get(k_id, 0)
            avail = self.copper_stats[k_id]['avail_vol_brl']
            if avail > 0:
                ratios[k_id] = used / avail
            else:
                ratios[k_id] = 0.0
            
        single_gyle_grains = []
        single_gyle_adjuncts = []
        single_gyle_hops = []

        def add_item(lst, name, weight, type_, alpha=None, time=None, util=None, temp=None, meta=None):
            for item in lst:
                if (item['name'] == name and item.get('type') == type_ and 
                    item.get('time') == time and item.get('util') == util):
                    item['weight'] += weight
                    return
            entry = {"name": name, "weight": weight, "type": type_}
            if alpha: entry['alpha'] = alpha
            if time: entry['time'] = time
            if util: entry['util'] = util
            if temp: entry['temp'] = temp
            if meta: entry['meta'] = meta
            lst.append(entry)

        for g in self.data['mash_phase']['grains']:
            total_weight = g['weight_lb']
            w_c1 = total_weight * (self.copper_stats['copper_1']['wort_pts_gal'] / self.total_wort_pts_system)
            w_c2 = total_weight * (self.copper_stats['copper_2']['wort_pts_gal'] / self.total_wort_pts_system)
            w_c3 = total_weight * (self.copper_stats['copper_3']['wort_pts_gal'] / self.total_wort_pts_system)
            pa2_weight = (w_c1 * ratios['copper_1']) + (w_c2 * ratios['copper_2']) + (w_c3 * ratios['copper_3'])
            meta = {'color': g.get('color_ebc', 0), 'potential': g.get('potential_sg', 1.036)}
            add_item(single_gyle_grains, g['name'], pa2_weight, 'grain', meta=meta)

        for copper in self.data['boil_phase']:
            k_id = copper['kettle_id']
            ratio = ratios[k_id]
            if ratio == 0: continue
            for adj in copper['adjuncts']:
                meta = {'color': adj.get('color_ebc', 0), 'potential': adj.get('potential_sg', 1.030)}
                add_item(single_gyle_adjuncts, adj['name'], adj['weight_lb'] * ratio, 'adjunct', meta=meta)
            for hop in copper['hops_whole']:
                add_item(single_gyle_hops, hop['name'], hop['weight_lb'] * ratio, 'boil', hop['alpha'], hop['time_min'], util=1.0)
            steps = copper.get('post_boil_steps', [])
            if not steps and 'post_boil_stand' in copper and copper['post_boil_stand'].get('active'):
                 s = copper['post_boil_stand']
                 steps = [{'step_type': 'stand', 'hops': s.get('add_whole_hops', []), 
                           'duration_min': s.get('duration_min', 30), 
                           'utilization_factor_relative': 0.1,
                           'temperature_c': s.get('avg_temp_c', 80)}] 
            for step in steps:
                if step['step_type'] == 'stand':
                    u = step.get('utilization_factor_relative', 0.1)
                    t_c = step.get('temperature_c', 80)
                    for hop in step.get('hops', []):
                        add_item(single_gyle_hops, hop['name'], hop['weight_lb'] * ratio, 'stand', 
                                 hop['alpha'], step.get('duration_min', 30), util=u, temp=t_c)

        total_pa2_vol_brl = beer_data['vol_brl']
        if total_pa2_vol_brl <= 0:
            self.report_lines.append("Error: Target beer has 0 volume.")
            return

        vol_scale_factor = target_vol_l / (total_pa2_vol_brl * BRL_TO_L)
        source_eff = self.data['mash_phase'].get('system_efficiency_target_percent', 90.5)
        eff_scale_factor = source_eff / target_efficiency

        self.single_gyle_recipe = {
            "recipe_name": f"Single Gyle: {target_beer} ({target_vol_l}L, {revised_boil_mins}min)",
            "brewer": "Parti-Gyle Analyser",
            "type": "All Grain",
            "target_stats": {
                "batch_size_L": target_vol_l,
                "boil_size_L": target_boil_size_l,
                "boil_time_min": revised_boil_mins,
                "target_og": round(target_og, 3),
                "calculated_ibu": 0,
                "target_ebc": round(beer_data['ebc'], 1),
                "efficiency_basis_percent": target_efficiency
            },
            "mash_fermentables": [],
            "boil_additions": {
                "adjuncts": [],
                "hops": []
            }
        }

        self.report_lines.append("Fermentables (excluding caramel in %):")
        total_fermentable_kg = 0
        grains_scaled = []
        for g in single_gyle_grains:
            kg = g['weight'] * LB_TO_KG * vol_scale_factor * eff_scale_factor
            grains_scaled.append({"name": g['name'], "kg": kg, "type": "grain", "meta": g.get('meta')})
            total_fermentable_kg += kg
        adjuncts_scaled = []
        for a in single_gyle_adjuncts:
            kg = a['weight'] * LB_TO_KG * vol_scale_factor
            is_caramel = "caramel" in a['name'].lower() or "colour" in a['name'].lower()
            adjuncts_scaled.append({"name": a['name'], "kg": kg, "is_caramel": is_caramel, "meta": a.get('meta')})
            if not is_caramel:
                total_fermentable_kg += kg

        for item in grains_scaled + [x for x in adjuncts_scaled if not x['is_caramel']]:
            pct = 0
            if total_fermentable_kg > 0:
                pct = (item['kg'] / total_fermentable_kg) * 100
            w_str = format_weight(item['kg'])
            self.report_lines.append(f"  {item['name']}: {w_str} ({pct:.1f}%)")
            
            fermentable_entry = {
                "name": item['name'], 
                "weight_kg": round(item['kg'], 3), 
                "percent": round(pct, 1),
            }
            if item.get('meta'):
                fermentable_entry['color_ebc'] = item['meta'].get('color', 0)
                fermentable_entry['potential_sg'] = item['meta'].get('potential', 1.036)

            if item.get('type') == "grain":
                self.single_gyle_recipe['mash_fermentables'].append(fermentable_entry)
            else:
                fermentable_entry['time_min'] = revised_boil_mins
                self.single_gyle_recipe['boil_additions']['adjuncts'].append(fermentable_entry)

        for item in [x for x in adjuncts_scaled if x['is_caramel']]:
            g_per_l = (item['kg'] * 1000) / target_vol_l
            w_str = format_weight(item['kg'])
            self.report_lines.append(f"  {item['name']}: {w_str} ({g_per_l:.2f} g/L)")
            
            adjunct_entry = {
                "name": item['name'], 
                "weight_g_per_L": round(g_per_l, 2), 
                "total_g": round(item['kg']*1000, 1), 
                "weight_kg": round(item['kg'], 3),
                "time_min": revised_boil_mins
            }
            if item.get('meta'):
                adjunct_entry['color_ebc'] = item['meta'].get('color', 0)
                adjunct_entry['potential_sg'] = item['meta'].get('potential', 1.030)
            
            self.single_gyle_recipe['boil_additions']['adjuncts'].append(adjunct_entry)

        self.report_lines.append("")
        self.report_lines.append(f"Hops ({target_hop_form}, {revised_boil_mins} min boil):")
        sg_ibu = 0
        for h in single_gyle_hops:
            base_g = h['weight'] * LB_TO_KG * 1000 * vol_scale_factor
            adjusted_g = base_g * hop_weight_factor
            orig_time = h['time']
            new_time = revised_boil_mins if h['type'] == 'boil' else h['time']
            if h['type'] == 'boil':
                orig_util_val = (1 - math.exp(-0.04 * orig_time)) / 4.15
                new_util_val = (1 - math.exp(-0.04 * new_time)) / 4.15
                time_correction = orig_util_val / new_util_val
                final_g = adjusted_g * time_correction
            else:
                final_g = adjusted_g
            
            wt_lb = final_g / 1000 / LB_TO_KG
            vol_brl = target_vol_l / BRL_TO_L
            u = h.get('util', 1.0)
            ibu = calculate_tinseth_ibu(h['alpha'], wt_lb, new_time, vol_brl, target_og, 1.0, u)
            sg_ibu += ibu
            rate_gl = final_g / target_vol_l
            usage_str = h['type'].title()
            temp_str = f" @ {h.get('temp')}C" if h.get('temp') else ""
            
            entry = {
                "name": h['name'], 
                "usage": usage_str, 
                "form": target_hop_form,
                "alpha": h['alpha'], 
                "weight_g": round(final_g, 1), 
                "rate_g_L": round(rate_gl, 2),
                "time_min": new_time
            }
            if h.get('temp'): entry['temp_c'] = h['temp']
            self.single_gyle_recipe['boil_additions']['hops'].append(entry)
            self.report_lines.append(f"  {h['name']} ({usage_str}): {final_g:.1f}g ({rate_gl:.2f} g/L) @ {new_time} min{temp_str} - {ibu:.1f} IBU")

        self.single_gyle_recipe['target_stats']['calculated_ibu'] = round(sg_ibu, 1)
        self.report_lines.append(f"Total Single Gyle IBU: {sg_ibu:.1f}")
        diff = sg_ibu - beer_data['ibu']
        self.report_lines.append(f"Variance vs Target: {diff:+.1f} IBU")
    
    def export_beerxml(self, filepath):
        rec = self.single_gyle_recipe
        stats = rec['target_stats']
        
        root = ET.Element("RECIPES")
        recipe = ET.SubElement(root, "RECIPE")
        
        ET.SubElement(recipe, "NAME").text = rec['recipe_name']
        ET.SubElement(recipe, "VERSION").text = "1"
        ET.SubElement(recipe, "TYPE").text = rec.get("type", "All Grain")
        ET.SubElement(recipe, "BREWER").text = rec.get("brewer", "Parti-Gyle Analyser")
        ET.SubElement(recipe, "BATCH_SIZE").text = f"{stats['batch_size_L']:.2f}"
        ET.SubElement(recipe, "BOIL_SIZE").text = f"{stats['boil_size_L']:.2f}" 
        ET.SubElement(recipe, "BOIL_TIME").text = str(stats['boil_time_min'])
        ET.SubElement(recipe, "EFFICIENCY").text = str(stats['efficiency_basis_percent'])
        
        hops_node = ET.SubElement(recipe, "HOPS")
        for h in rec['boil_additions']['hops']:
            node = ET.SubElement(hops_node, "HOP")
            ET.SubElement(node, "NAME").text = h['name']
            ET.SubElement(node, "VERSION").text = "1"
            ET.SubElement(node, "ALPHA").text = str(h['alpha'])
            ET.SubElement(node, "AMOUNT").text = f"{h['weight_g'] / 1000.0:.5f}" # Rounded to 5 decimal kg
            use_map = "Boil"
            if "stand" in h['usage'].lower(): use_map = "Aroma"
            ET.SubElement(node, "USE").text = use_map
            ET.SubElement(node, "TIME").text = str(h['time_min'])
            ET.SubElement(node, "FORM").text = h['form'].title()
            if h.get('temp_c'):
                ET.SubElement(node, "TEMPERATURE").text = str(h['temp_c']) 
        
        ferms_node = ET.SubElement(recipe, "FERMENTABLES")
        for f in rec['mash_fermentables']:
            node = ET.SubElement(ferms_node, "FERMENTABLE")
            ET.SubElement(node, "NAME").text = f['name']
            ET.SubElement(node, "VERSION").text = "1"
            ET.SubElement(node, "TYPE").text = "Grain"
            ET.SubElement(node, "AMOUNT").text = f"{f['weight_kg']:.3f}"
            ET.SubElement(node, "YIELD").text = f"{(f.get('potential_sg', 1.036) - 1) * 1000 / 0.46:.2f}" 
            lov = ebc_to_lovibond(f.get('color_ebc', 5))
            ET.SubElement(node, "COLOR").text = f"{lov:.1f}"

        for a in rec['boil_additions']['adjuncts']:
            node = ET.SubElement(ferms_node, "FERMENTABLE")
            ET.SubElement(node, "NAME").text = a['name']
            ET.SubElement(node, "VERSION").text = "1"
            ET.SubElement(node, "TYPE").text = "Sugar" 
            ET.SubElement(node, "AMOUNT").text = f"{a.get('weight_kg', 0):.3f}"
            ET.SubElement(node, "YIELD").text = "75.0" 
            lov = ebc_to_lovibond(a.get('color_ebc', 0))
            ET.SubElement(node, "COLOR").text = f"{lov:.1f}"

        ET.SubElement(recipe, "STYLE").text = "" 

        xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
        with open(filepath, "w", encoding='utf-8') as f:
            f.write(xmlstr)

def main():
    root = tk.Tk()
    root.withdraw() 
    
    input_path = filedialog.askopenfilename(title="Select JSON", filetypes=[("JSON", "*.json")])
    if not input_path: return

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        messagebox.showerror("Error", f"Load Failed: {e}")
        return

    available_beers = [b['name'] for b in data['blending_matrix']['final_beers']]
    json_target = data.get('single_gyle_settings', {}).get('target_beer')
    target_beer = None
    
    if json_target and json_target in available_beers:
        target_beer = json_target
        if messagebox.askyesno("Target Found", f"JSON specifies target beer: '{json_target}'.\n\nUse '{json_target}'?"):
             target_beer = json_target
        else:
             target_beer = None

    if not target_beer:
        selection_dialog = BeerSelectionDialog(root, available_beers)
        target_beer = selection_dialog.selected_beer
        if not target_beer:
            messagebox.showinfo("Cancelled", "No beer selected. Exiting.")
            return

    analyzer = PartiGyleAnalyzer(data, target_beer_override=target_beer)
    try:
        analyzer.run_analysis()
    except Exception as e:
        messagebox.showerror("Error", f"Analysis Failed: {e}")
        return

    output_dir = filedialog.askdirectory(title="Output Directory")
    if not output_dir: return
    
    base_name = simpledialog.askstring("Save", "Base filename:", initialvalue=f"{target_beer}_Analysis")
    if not base_name: base_name = "Output"

    try:
        with open(os.path.join(output_dir, f"{base_name}.txt"), 'w', encoding='utf-8') as f:
            f.write("\n".join(analyzer.report_lines))
        with open(os.path.join(output_dir, f"{base_name}.json"), 'w', encoding='utf-8') as f:
            json.dump(analyzer.single_gyle_recipe, f, indent=2)
        analyzer.export_beerxml(os.path.join(output_dir, f"{base_name}.xml"))
        
        messagebox.showinfo("Done", "Files Saved:\n- Report (.txt)\n- Recipe (.json)\n- BeerXML (.xml)")
    except Exception as e:
        messagebox.showerror("Error", f"Save Failed: {e}")

if __name__ == "__main__":
    main()