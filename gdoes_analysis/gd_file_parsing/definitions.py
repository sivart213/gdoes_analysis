DIRECT_TRANSLATIONS = {
    # ---- Unique Keys ----
    "CBCLEUNIK": "Cal_Base_Key",  # Clé unique CB (unique key)
    "EECLEUNIK": "Elem_Cal_Key",  # Clé unique EE
    "EMCLEUNIK": "Elem_Meth_Key",  # Clé unique EM
    "ELCLEUNIK": "Elem_Line_Key",  # Clé unique EL
    "LRCLEUNIK": "Layer_Res_Key",  # Clé unique LR
    "MECLEUNIK": "Meth_Entr_Key",  # Clé unique ME
    "RBCLEUNIK": "Recalib_Key",  # Clé unique RB
    "RECLEUNIK": "Res_Elem_Key",  # Clé unique RE
    "RFCLEUNIK": "Res_Func_Key",  # Clé unique RF
    "RLCLEUNIK": "Rl_Unique_Key",  # clé unique RL
    "RPCLEUNIK": "Res_Prof_Key",  # Clé unique RP
    "TBCLEUNIK": "Task_Base_Key",  # Clé unique TB
    "TRCLEUNIK": "Task_Res_Key",  # Clé unique TR
    "TSCLEUNIK": "Task_Seq_Key",  # Clé unique TS
    "TTCLEUNIK": "Task_Type_Key",  # Clé unique TT
    # ---- Element / Line ----
    "NOMELEM": "Elem_Name",  # Nom élément (element name)
    "NOMELM": "Element_Name",  # Nom élément (variant)
    "NOMRAIE": "Spectr_Line",  # Nom raie (spectral line name)
    "RAIEELT": "Elemental_Line",  # Raie élément (element spectral line)
    "POS_RAIE": "Line_Pos",  # Position de raie (line position)
    "LGONDE": "Wavelength",  # Longueur d’onde (wavelength)
    "INTENSITE": "Intensity",  # Intensité (intensity)
    "NUMCANAL": "Channel_Num",  # Numéro canal (channel number)
    "ELTMAJEUR": "Major_Elemental",  # Élément majeur (major element)
    "NUMELECTRO": "Electrode_Num",  # Numéro électrode (electrode number)
    # ---- Interference / Importance ----
    "IEELEMENT": "Interf_Elem",  # Interference element
    "IEDEGREE": "Interf_Degree",  # Interference degree
    "IEImportance": "Interf_Import",  # Importance of interference
    "IEMImportance": "Interf_Mol_Import",  # Molecular interference importance
    # ---- Calibration / Standards ----
    "NOMETALON": "Cal_Name",  # Nom étalon (calibration name)
    "A_ETALPM": "Cal_A",  # Coefficient A (étalonnage)
    "B_ETALPM": "Cal_B",  # Coefficient B (étalonnage)
    "STDREETAL1": "Std_Cal1",  # Standard calibration 1
    "STDREETAL2": "Std_Cal2",  # Standard calibration 2
    "STDINTERNE": "Std_Internal",  # Internal standard
    "ORDRECALIB": "Cal_Order",  # Calibration order
    "REFETALON": "Ref_Cal",  # Reference calibration
    "POIDETAL": "Cal_Weight",  # Poids étalon (calibration weight)
    "ETALMETH": "Cal_Method",  # Méthode étalonnage (calibration method)
    "ELTETALO": "Cal_Elemental_Name",  # Étalon élément (calibration element info)
    "EMPLACEMEN": "Cal_Location",  # Emplacement étalon (calibration location)
    "VITEROSION": "Erosion_Velocity",  # Vitesse érosion (erosion rate)
    "VITEROREL": "Erosion_Velocity_Rel",  # Vitesse érosion relative
    # ---- Instrument / Optics ----
    "APPAREIL": "Device",  # Instrument / device
    "FENTEIN": "Slit_In",  # Entrance slit
    "FENTEOUT": "Slit_Out",  # Exit slit
    "HTENSION": "High_Volt",  # High tension (voltage)
    "AMPLIFIER": "Amplifier",  # Amplifier setting
    # ---- Physical parameters ----
    "MASSEATOM": "Atomic_Mass",  # Masse atomique
    "DENSITE": "Density",  # Densité
    "COULEUR": "Color",  # Couleur
    # ---- Method / Mode ----
    "NOMMETH": "Method_Name",  # Nom méthode
    "ELTMETH": "Elemental_Method",  # Méthode élément
    "MODEANALYS": "Analysis_Mode",  # Mode analyse
    "MODEGENE": "Gen_Mode",  # Mode génération
    "CalcMode": "Calc_Mode",  # Calculation mode
    "METHODE": "Method",  # Méthode
    # ---- Time / Duration ----
    "TPSBALAYAG": "Scan_Time",  # Temps balayage (scan time)
    "TPSPREINTE": "Pre_Int_Time",  # Pre-integration time
    "TPSFOND": "Bkg_Time",  # Background time
    "DURANALYSE": "Analysis_Dur",  # Duration of analysis
    "HEURE": "Time",  # Heure (time)
    "DATEHEURE": "Date_Time",  # Date et heure
    # ---- Power / Pressure / Current ----
    "TENSION": "Voltage",  # Tension
    "COURANT": "Current",  # Courant
    "PRESSION": "Pressure",  # Pression
    "PUISSANC": "Power",  # Puissance
    # ---- DIP parameters ----
    "DipMinOscPeriod": "Dip_Min_Period",  # Minimum oscillation period
    "DipZoneLeft": "Dip_Left_Zone",  # DIP left zone
    "DipZoneRight": "Dip_Right_Zone",  # DIP right zone
    "DipRightLimit": "Dip_Right_Limit",  # DIP right limit
    "DipRightLeft": "Dip_Right_Left",  # DIP right-left parameter
    # ---- Sample / Result ----
    "NOMECHANT": "Sample_Name",  # Nom échantillon
    "NOMECHAN2": "Sample_Name2",  # Nom échantillon 2
    "OPERATEUR": "Operator",  # Operator
    "CHEMIN": "Path",  # File path
    "COMMENTAIR": "Comment",  # Comment
    "TYPERES": "Result_Type",  # Type résultat
    "DESCRIPT": "Descrip",  # Description
    "CONCTHEO": "Conc_Theo",  # Theoretical concentration
    "CONCCALC": "Conc_Calc",  # Calculated concentration
    "CONCCORR": "Conc_Corr",  # Corrected concentration
    # ---- Misc ----
    "ECARTLIM": "Dev_Limit",  # Ecart limite (deviation limit)
    "DETLIMIT": "Det_Limit",  # Detection limit
    "HIGHLIMIT": "High_Limit",  # High limit
    "HCORRECT": "HCorrect",  # High-voltage correction
    "SelfAbsorp": "Self_Absorp",  # Self absorption
    "InUse": "In_Use",  # In use flag
    "NOMELEMAPP": "App_Elem_Name",  # Nom élément appliqué (applied element name)
    "FAMILLE": "Family",  # Famille (family)
    "ORDRE": "Ordre",  # Ordre (order)
    "RELSPTRATE": "Rel_Sputter_Rate",  # Relative sputter rate
    "MOYENNAGE": "Avg",  # Averaging
    "VALIDE": "Valid",  # Valid flag
    "ELTCENTRAG": "Elemental_Centering",  # centrage = centering
    "MOY_RES": "Average_Res",  # moyenne = average
    "RECALIBRER": "Recalibrate",  # recalibrer
    "STDINTGLOB": "Std_Internal_Global",  # standard interne global
    "TPSOscHighFlush": "Time_Osc_High_Flush",  # temps
    "TPSOscLowFlush": "Time_Osc_Low_Flush",
    "TPSStrongFlush": "Time_Strong_Flush",
    "VALSEUIL": "Value_Threshold",  # valeur seuil
    "VDCREF": "VDC_Reference",  # référence
    "CBCLE1": "Cb_Key1",  # clé = key
    "CBCLE2": "Cb_Key2",
    "CBKeys": "Cb_Keys",
    "CentreDepth": "Center_Depth",  # centre → center
    "ECART_RES": "Deviation_Res",  # écart = deviation
    "ELMORDER": "Element_Order",  # élément ordre
    "ELT_RES": "Elemental_Res",  # élément résultat
    "EMSEUIL": "Em_Threshold",  # seuil = threshold
    "ErreurVE": "Error_VE",  # erreur = error
    "FiltreName": "Filter_Name",  # filtre = filter
    "HTASSERVIE": "HT_Servo",  # asservie = servo‑controlled
    "INDICEMETH": "Method_Index",  # indice = index
    "INDMODIF": "Modif_Index",  # modif = modification
    "INTMODIF": "Modif_Intensity",  # ambiguous but French root
    "IORDER": "I_Order",  # unclear, leave structure
    "MATRIXELEM": "Matrix_Element",  # élément
    "METHORDER": "Method_Order",  # méthode ordre
    "MODULE": "Module",  # ambiguous
    "MODULEPI": "Module_PI",
    "ModuleSI": "Module_SI",
    "Nomelt": "Elemental_Name",  # nom élément
    "NometalElt": "Elemental_Cal_Name",
    "NometalEm": "Emission_Cal_Name",
    "PRESSIONPI": "Pressure_PI",  # pression = pressure
    "PUISSANCPI": "Power_PI",  # puissance = power
    "PressionSI": "Pressure_SI",
    "PuissancSI": "Power_SI",
    "RAIE_RES": "Line_Res",  # raie = spectral line
    "RAPCYCL": "Cycle_Ratio",  # rapport cycle
    "RAPCYCLPI": "Cycle_Ratio_PI",
    "RapCyclSI": "Cycle_Ratio_SI",
    "SIPulseSynchro": "SI_Pulse_Synchro",
    "TPSSURFACE": "Time_Surface",  # temps surface
    # ---- General syntax conversions ----
    "DEGREE": "Degree",
    "VALUE": "Value",
    "SIGMA": "Sigma",
    "CONCENTRAT": "Concentration",
    "DATE": "Date",
    "OPERATION": "Operation",
    "PARAMS": "Params",
    "SAMPLE": "Sample",
    "ACCURACY": "Accuracy",
    "DURATION": "Duration",
    "DENSITY": "Dens.",
    "DEPTH": "Depth",
    "CONFIDENCE": "Confidence",
    "ALPHA": "Alpha",
    "ANODESIZE": "Anode_Size",
    "AcqType": "Acq_Type",
    "Application": "Application",
    "AverageDepth": "Average_Depth",
    "BETA": "Beta",
    "Background": "Background",
    "Charge": "Charge",
    "ClassName": "Class_Name",
    "Comments": "Comments",
    "CONCMAX": "Conc_Max",
    "CONCMIN": "Conc_Min",
    "Description": "Descr.",
    "DipEnvelope": "Dip_Envelope",
    "DipExtraK": "Dip_Extra_K",
    "DipNormalA": "Dip_Normal_A",
    "DipNormalD": "Dip_Normal_D",
    "DipRightK": "Dip_Right_K",
    "Domain": "Domain",
    "Duration": "Dur.",
    "Elements": "Elements",
    "EltAtoms": "Elt_Atoms",
    "EltCount": "Elt_Count",
    "ErosionRate": "Erosion_Rate",
    "FitForQC": "Fit_For_QC",
    "FixedMB": "Fixed_MB",
    "FixedMBPI": "Fixed_MB_PI",
    "FixedMBSI": "Fixed_MB_SI",
    "Formula": "Formula",
    "GResolution": "G_Resolution",
    "InterferCount": "Interfer_Count",
    "InterferMCount": "Interfer_M_Count",
    "InterferMolecul": "Interfer_Molecule",
    "Interference": "Interference",
    "IsLayer": "Is_Layer",
    "IsTransparent": "Is_Transparent",
    "LAYERNAME": "Layer_Name",
    "LAYERTYPE": "Layer_Type",
    "LAYORDER": "Layer_Order",
    "LINETYPE": "Line_Type",
    "Lines": "Lines",
    "LowerWV": "Lower_WV",
    "MInIntensUnc": "Min_Intens_Unc",
    "MLineType": "M_Line_Type",
    "Mirror": "Mirror",
    "Moleculname": "Molecule_Name",
    "MonoShift11": "Mono_Shift_11",
    "MonoShift12": "Mono_Shift_12",
    "MonoShift21": "Mono_Shift_21",
    "MonoShift22": "Mono_Shift_22",
    "NAME": "Name",
    "ObjectName": "Object_Name",
    "OscFlush": "Osc_Flush",
    "PeakShift": "Peak_Shift",
    "PeakValue": "Peak_Value",
    "PeakWidth": "Peak_Width",
    "Points": "Points",
    "PulseSynchro": "Pulse_Synchro",
    "PMName": "PM_Name",
    "Rec #.": "Rec_Num",
    "Refraction": "Refraction",
    "RefractiveIndex": "Refractive_Index",
    "RefractiveK": "Refractive_K",
    "RefractiveN": "Refractive_N",
    "StageCount": "Stage_Count",
    "SurfCleanDur": "Surf_Clean_Dur",
    "UNIT": "Unit",
    "Uncertainty": "Uncertainty",
    "UniqueKey": "Unique_Key",
    "UpperWV": "Upper_WV",
    "WAVELENGTH": "Wv_length",
    "WVMolecule": "WV_Molecule",
    "XRFName": "XRF_Name",
    "XSpacing": "X_Spacing",
    "X_AXIS": "X_Axis",
    "YSpacing": "Y_Spacing",
    "Y_AXIS": "Y_Axis",
    "ZMax": "Z_Max",
    "ZMin": "Z_Min",
    "ORDER": "Order",
    "PHASE": "Phase",
    "PHASEPI": "Phase_PI",
    "CCDIntegr": "CCD_Integr",
    "CmpndElts": "Cmpnd_Elts",
    "MeasDT": "Meas_DT",
    "MeasOptions": "Meas_Options",
    "PIPulseSynchro": "PI_Pulse_Synchro",
    "PhaseSI": "Phase_SI",
    "VALIDATION": "Validation",
}


PART_TRANSLATIONS = {
    # ---- Keys / Identifiers ----
    "CLEUNIK": "Key",  # Clé unique (unique key)
    "NOM": "Name",  # Nom (name)
    # ---- Spectral / Optical ----
    "RAIE": "Spectral_Line",  # Spectral line
    "LGONDE": "Wavelength",  # Longueur d’onde
    # ---- Calibration ----
    "ETALON": "Cal_Std",  # Étalon (calibration standard)
    "ETAL": "Cal",  # Étalonnage (calibration)
    "ECART": "Dev",  # Écart (deviation)
    "SEUIL": "Thresh",  # Threshold
    # ---- Instrumentation ----
    "APPAREIL": "Device",  # Instrument
    "FENTE": "Slit",  # Optical slit
    # ---- Physical parameters ----
    "MASSE": "Mass",  # Mass
    "COUL": "Color",  # Color
    # ---- Time / Duration ----
    "TPS": "Time",  # Temps (time)
    "MOYENNAGE": "Avg",  # Averaging
    "HEURE": "Time",  # Heure (time)
    # ---- Power / Pressure / Current ----
    "TENSION": "Volt",  # Voltage
    "COURANT": "Current",  # Current
    "PRESSION": "Press",  # Pressure
    "PUISSANC": "Power",  # Power
    # ---- Misc ----
    "OPERATEUR": "Operator",  # Operator
    "COMMENTAIR": "Comment",  # Comment
    "CHEMIN": "Path",  # Path
    "ORDRE": "Order",  # Order
    "VALIDE": "Valid",  # Valid flag
}

LETTER_CODES = {
    "am": "cal_methods",  # Calibration method (calibration method name) Etalmeth.fic
    "cb": "cal_base",  # Calibration base / calibration block (coefficients, sigma, degree) Calibrat.fic
    "ea": "etalon",  # Calibration standard (name, family, density, erosion rate) Etalon.fic
    "ee": "elem_cal",  # Element calibration (element name, intensity, concentrations) Elmetal.fic
    "el": "elem_line",  # Element metadata (names, lines, channels) Element.fic
    "em": "elem_meas",  # Élément Mesure (element measurement data) Eltmeth.fic
    "eo": "eltetalo",  # Calibration element (element name, concentration, uncertainty) Eltetalo.fic
    "li": "line_info",  # Line metadata (atomic mass, density, color) Listelt.fic
    "lr": "layer_res",  # Layer results (layer type, name, density, depth, duration) Layer.fic
    "me": "method_entry",  # Method definition (timings, power, DIP params, options) Methode.fic
    "ra": "raie_analysis",  # Spectral line table (wavelength, intensity, interference) RAIE.fic
    "re": "res_entry",  # Result record (sample, operator, date, path, result type) Resultat.fic
    "rf": "res_function",  # Reference axes for result/emission (x/y axis definitions) RES_SURF.fic
    "rl": "res_line",  # Result line data (wavelength, intensity, peak shift/width/value) Res_elem.fic
    "rr": "res_crater",  # Result crater data (depth, charge, background, elements) RES_CRATER.fic
    "tr": "treatment_result",  # Processing/display operations (operation, params, curve roles) Tr_param.fic
    "ts": "task_sequence",  # Task sequence linking tasks to blocks Tr_step.fic
    "tt": "task_type",  # Task definitions (task ID, name, description, method link) Treatment.fic
    "tb": "task_block",  # Task block type (inferred from TS linking)
    "ie": "interf_elem",  # Interference definitions (elements, degrees, importance)
}


# fmt: off
COL_NAMES = {
    "Calibrat": [
        "CBCLEUNIK", "EMCLEUNIK", "DEGREE", "IEELEMENT", "IEDEGREE", "VALUE", "SIGMA",
    ],
    "CORRELAT": [
        "CBCLE1", "CBCLE2", "SIGMA", "CBKeys",
    ],
    "Element": [
        "ELCLEUNIK", "NOMELEM", "NOMRAIE", "NUMCANAL", "NUMELECTRO", "ORDRE", "APPAREIL", "POS_RAIE",
        "A_ETALPM", "B_ETALPM", "SAMPLE", "PMName", "FiltreName", "Mirror", "MonoShift11", "MonoShift12",
        "MonoShift21", "MonoShift22", "NOMELEMAPP"
    ],
    "Elmetal": [
        "EECLEUNIK", "NOMETALON", "EMCLEUNIK", "POIDETAL", "INTENSITE", "INTMODIF", "SIGMA", "CONCTHEO", "CONCCALC",
        "CONCCORR", "VALIDE", "NometalEm",
    ],
    "Elretal": [
        "NOMETALON", "EMCLEUNIK", "INTENSITE", "SIGMA", "NometalElt"
    ],
    "Eltetalo": [
        "NOMETALON", "ELTETALO", "CONCENTRAT", "IORDER", "Uncertainty", "NometalElt",
    ],
    "Eltmeth": [
        "EMCLEUNIK", "MECLEUNIK", "ELCLEUNIK", "ELTMETH", "RAIEELT", "APPAREIL", "HTENSION", "STDREETAL1", "STDREETAL2",
        "FENTEIN", "FENTEOUT", "STDINTERNE", "ECARTLIM", "ORDRECALIB", "AMPLIFIER", "IORDER", "DETLIMIT", "HIGHLIMIT",
        "HCORRECT", "MInIntensUnc", "CalcMode", "ELMORDER",
    ],
    "Etalmeth": [
        "MECLEUNIK", "ETALMETH"
    ],
    "Etalon": [
        "NOMETALON", "FAMILLE", "DENSITE", "VITEROSION", "VITEROREL", "EMPLACEMEN", "ELTMAJEUR", "ACCURACY", "FitForQC",
        "ErreurVE", "RefractiveN", "RefractiveK", "IsLayer",
    ],
    "Layer": [
        "LRCLEUNIK", "MECLEUNIK", "IORDER", "LAYERTYPE", "LAYERNAME", "RELSPTRATE", "DENSITY", "DEPTH", "DURATION",
        "ErosionRate", "RefractiveIndex", "IsTransparent", "METHORDER",
    ],
    "LAYERELT": [
        "LRCLEUNIK", "EMCLEUNIK", "IORDER", "CONCMIN", "CONCMAX", "LAYORDER",
    ],
    "Listelt": [
        "NOMELM", "MASSEATOM", "DENSITE", "COULEUR", "AMPLIFIER"
    ],
    "Methode": [
        "MECLEUNIK", "NOMMETH", "INDMODIF", "VALIDATION", "RECALIBRER", "STDINTGLOB", "ELTCENTRAG",
        "MODEANALYS", "TPSBALAYAG", "TPSPREINTE", "TPSFOND", "StageCount", "TPSSURFACE", "DURANALYSE",
        "MOYENNAGE", "TENSION", "COURANT", "PRESSION", "PUISSANC", "MODULE", "PHASE", "RAPCYCL", "FixedMB",
        "PRESSIONPI", "PUISSANCPI", "MODULEPI", "PHASEPI", "RAPCYCLPI", "FixedMBPI", "DATE", "HEURE",
        "COMMENTAIR", "ANODESIZE", "MODEGENE", "HTASSERVIE", "CCDIntegr", "TTCLEUNIK", "REFETALON",
        "VITEROSION", "CmpndElts", "MATRIXELEM", "EMSEUIL", "VALSEUIL", "VDCREF", "PulseSynchro",
        "PIPulseSynchro", "MeasOptions", "Application", "PressionSI", "PuissancSI", "ModuleSI", "PhaseSI",
        "RapCyclSI", "FixedMBSI", "SIPulseSynchro", "SurfCleanDur", "TPSStrongFlush", "OscFlush", "TPSOscLowFlush",
        "TPSOscHighFlush", "DipNormalA", "DipNormalD", "DipMinOscPeriod", "DipZoneLeft", "DipZoneRight",
        "DipRightLimit", "DipRightLeft", "Domain", "XRFName", "Refraction", "INDICEMETH",
    ],
    "MOLECUL": (
        ["Moleculname", "Description", "DENSITY", "EltCount"] +
        [f"Elements_{i+1}" for i in range(16)] + [f"EltAtoms_{i+1}" for i in range(16)] + ["Formula"]
    ),
    "PMTType": [
        "PMName", "LowerWV", "UpperWV", "Comments",
    ],
    "ProfMeth": [
        "ELCLEUNIK", "EMCLEUNIK", "ORDRE"
    ],
    "RAIE": (
        ["Nomelt", "LGONDE", "IORDER", "INTENSITE", "LINETYPE", "InterferCount"] +
        [f"Interference_{i+1}" for i in range(32)] +
        [f"IEImportance_{i+1}" for i in range(32)] + ["InterferMCount"] +
        [f"InterferMolecul_{i+1}" for i in range(16)] +
        [f"IEMImportance_{i+1}" for i in range(16)] +
        ["SelfAbsorp", "HCORRECT", "InUse", "WAVELENGTH"]
    ),
    "Raiemlcl": [
        "Moleculname", "LGONDE", "IORDER", "INTENSITE", "Charge", "MLineType", "WVMolecule",
    ],
    "Recalibr": [
        "RBCLEUNIK", "EMCLEUNIK", "ALPHA", "BETA", "DATE", "HEURE", "DATEHEURE",
    ],
    "RES_CRATER": [
        "RECLEUNIK", "AcqType", "GResolution", "ZMin", "ZMax", "Points", "Lines", "XSpacing", "YSpacing", "Duration", "AverageDepth", "CentreDepth",
    ],
    "Res_elem": [
        "RLCLEUNIK", "RECLEUNIK", "ELT_RES", "RAIE_RES", "EMCLEUNIK", "ECART_RES", "MOY_RES", "UNIT",
    ],
    "Res_prof": [
        "RPCLEUNIK", "RECLEUNIK", "ELCLEUNIK", "PeakValue", "PeakShift", "PeakWidth", "Background",
    ],
    "RES_SURF": [
        "RFCLEUNIK", "RECLEUNIK", "EMCLEUNIK", "X_AXIS", "Y_AXIS"
    ],
    "Resultat": [
        "Rec #.", "RECLEUNIK", "NOMECHANT", "NOMECHAN2", "METHODE", "OPERATEUR", "DATE", "HEURE",
        "TYPERES", "CHEMIN", "COMMENTAIR", "X_AXIS", "Y_AXIS", "TTCLEUNIK", "CONFIDENCE", "MeasDT",
        "DipNormalA", "DipNormalA", "DipNormalA", "DipNormalA", "DipNormalD", "DipNormalD",
        "DipNormalD", "DipNormalD", "DipMinOscPeriod", "DipZoneLeft", "DipZoneRight", "DipExtraK",
        "DipRightLimit", "DipRightLeft", "DipRightK", "ErosionRate", "DipEnvelope",
    ],
    "Terms": [
        "ClassName", "ObjectName", "UniqueKey",
    ],
    "Tr_param": (
        ["TRCLEUNIK", "TSCLEUNIK", "EMCLEUNIK", "IEELEMENT", "OPERATION", "IORDER", "PARAMS"] +
        [f"ELCLEUNIK_{i+1}" for i in range(16)]
    ),
    "Tr_step": [
        "TSCLEUNIK", "TTCLEUNIK", "TBCLEUNIK", "IORDER",
    ],
    "Treatmnt": [
        "TTCLEUNIK", "NAME", "DESCRIPT", "MECLEUNIK",
    ],
}
# fmt: on
