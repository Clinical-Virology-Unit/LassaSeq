from Bio import Entrez
from Bio import SeqIO
from tqdm import tqdm
import argparse
import os
from datetime import datetime
import calendar
import time
import sys

def get_segment_type(record):
    """Determine if sequence is L or S segment based on proteins in header"""
    description = record.description.lower()
    
    # First check for direct segment mentions
    if 'segment l' in description or 'l segment' in description:
        return 'L'
    if 'segment s' in description or 's segment' in description:
        return 'S'
    
    # S segment proteins - expanded list
    s_proteins = [
        'nucleoprotein', 
        'glycoprotein',
        'nucleocapsid',
        'gpc',
        'np',
        'gc',
        'gn',
        'g1',
        'g2'
    ]
    
    # L segment proteins - expanded list
    l_proteins = [
        'polymerase',
        'rna-dependent rna polymerase',
        'rna dependent rna polymerase',
        'rdrp',
        'z protein',
        'zinc finger protein',
        'zinc-finger protein',
        'matrix protein',
        'l protein',
        'large protein'
    ]
    
    for protein in s_proteins:
        if protein in description:
            return 'S'
    for protein in l_proteins:
        if protein in description:
            return 'L'
    
    # If no protein found in header, try original header stored during download
    if hasattr(record, 'original_header'):
        description = record.original_header.lower()
        # Check for direct segment mentions in original header
        if 'segment l' in description or 'l segment' in description:
            return 'L'
        if 'segment s' in description or 's segment' in description:
            return 'S'
        
        for protein in s_proteins:
            if protein in description:
                return 'S'
        for protein in l_proteins:
            if protein in description:
                return 'L'
    
    return None

def convert_date_to_decimal_year(date_str):
    """Convert date to decimal year format"""
    try:
        # First, clean the date string
        date_str = date_str.strip()
        
        # If it's just a year
        if date_str.isdigit() and len(date_str) == 4:
            return f"{int(date_str)}.000"
        
        # Try different date formats
        formats = [
            ('%Y-%m-%d', True),    # 2013-08-15 -> full precision
            ('%Y-%m', False),      # 2013-08 -> month precision
            ('%d-%b-%Y', True),    # 15-Aug-2013 -> full precision
            ('%b-%Y', False),      # Aug-2013 -> month precision
        ]
        
        for date_format, is_full_date in formats:
            try:
                date = datetime.strptime(date_str, date_format)
                year = date.year
                
                if is_full_date:
                    # Calculate exact day for full dates
                    day_of_year = date.timetuple().tm_yday
                    total_days = 366 if calendar.isleap(year) else 365
                    decimal_year = year + (day_of_year / total_days)
                    return f"{decimal_year:.3f}"
                else:  # Month precision
                    # Use middle of the month
                    middle_date = datetime(year, date.month, 15)
                    day_of_year = middle_date.timetuple().tm_yday
                    total_days = 366 if calendar.isleap(year) else 365
                    decimal_year = year + (day_of_year / total_days)
                    return f"{decimal_year:.3f}"
            except ValueError:
                continue
        
        return "UnknownDate"
            
    except Exception as e:
        print(f"Date conversion error for {date_str}: {str(e)}")
        return "UnknownDate"

def get_standardized_country_name(country):
    """Convert country name to standardized format"""
    # Dictionary mapping various country name formats to standardized names
    country_mappings = {
        # Sierra Leone variations
        'sierra leone': 'SierraLeone',
        'sierra-leone': 'SierraLeone',
        'sierraleone': 'SierraLeone',
        'Sierra Leone': 'SierraLeone',
        'Sierra-Leone': 'SierraLeone',
        'SIERRA LEONE': 'SierraLeone',
        
        # Nigeria variations
        'nigeria': 'Nigeria',
        'Nigeria': 'Nigeria',
        'NIGERIA': 'Nigeria',
        
        # Liberia variations
        'liberia': 'Liberia',
        'Liberia': 'Liberia',
        'LIBERIA': 'Liberia',
        
        # Guinea variations
        'guinea': 'Guinea',
        'Guinea': 'Guinea',
        'GUINEA': 'Guinea',
        
        # Mali variations
        'mali': 'Mali',
        'Mali': 'Mali',
        'MALI': 'Mali',
        
        # Ghana variations
        'ghana': 'Ghana',
        'Ghana': 'Ghana',
        'GHANA': 'Ghana',
        
        # Benin variations
        'benin': 'Benin',
        'Benin': 'Benin',
        'BENIN': 'Benin',
        
        # Burkina Faso variations
        'burkina faso': 'BurkinaFaso',
        'Burkina Faso': 'BurkinaFaso',
        'BURKINA FASO': 'BurkinaFaso',
        'burkinafaso': 'BurkinaFaso',
        'burkina-faso': 'BurkinaFaso',
        'Burkina-Faso': 'BurkinaFaso',
        
        # Ivory Coast variations
        "cote d'ivoire": 'IvoryCoast',
        "Cote d'Ivoire": 'IvoryCoast',
        "COTE D'IVOIRE": 'IvoryCoast',
        "côte d'ivoire": 'IvoryCoast',
        "Côte d'Ivoire": 'IvoryCoast',
        'ivory coast': 'IvoryCoast',
        'Ivory Coast': 'IvoryCoast',
        'IVORY COAST': 'IvoryCoast',
        'ivorycoast': 'IvoryCoast',
        'ivory-coast': 'IvoryCoast',
        'Ivory-Coast': 'IvoryCoast',
        
        # Togo variations
        'togo': 'Togo',
        'Togo': 'Togo',
        'TOGO': 'Togo'
    }
    
    # First try exact match
    if country in country_mappings:
        return country_mappings[country]
    
    # Then try lowercase match
    return country_mappings.get(country.lower(), country)

def get_metadata(record):
    """Extract metadata from record"""
    # Get accession
    accession = record.id
    
    # Initialize location and date
    location = "UnknownLoc"
    collection_date = "UnknownDate"
    
    # Look for location and date in source features
    for feature in record.features:
        if feature.type == "source":
            # Get location from geo_loc_name
            if 'geo_loc_name' in feature.qualifiers:
                geo_loc = feature.qualifiers['geo_loc_name'][0]
                # Only use location if it's not 'missing'
                if 'missing' not in geo_loc.lower():
                    # Extract country (part before the colon)
                    location = geo_loc.split(':')[0].strip()
                    # Clean up location string
                    location = get_standardized_country_name(location)
            
            # Get collection date
            if 'collection_date' in feature.qualifiers:
                date_str = feature.qualifiers['collection_date'][0]
                if date_str.lower() != 'missing':
                    collection_date = convert_date_to_decimal_year(date_str)
    
    return f"{accession}_{location}_{collection_date}"

def fetch_sequences():
    Entrez.email = "anonymous@example.com"
    max_retries = 3
    retry_delay = 5  # seconds
    
    print("Searching for Lassa virus sequences...")
    search_term = "Mammarenavirus lassaense[Organism]"
    
    # Try the initial search with retries
    for attempt in range(max_retries):
        try:
            handle = Entrez.esearch(db="nucleotide", term=search_term, usehistory="y")
            record = Entrez.read(handle)
            handle.close()
            break
        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt
                print(f"Error: Unable to connect to NCBI after {max_retries} attempts.")
                print(f"Please check your internet connection or try again later.")
                print(f"Error details: {str(e)}")
                raise
            print(f"Connection attempt {attempt + 1} failed. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    
    count = int(record["Count"])
    webenv = record["WebEnv"]
    query_key = record["QueryKey"]
    
    print(f"Found {count} total sequences to process")
    
    batch_size = 100
    sequences = []
    segment_counts = {'L': 0, 'S': 0, 'Unknown': 0}
    location_counts = {'L': {}, 'S': {}}
    
    print("Downloading sequences in batches...")
    for start in tqdm(range(0, count, batch_size), desc="Downloading batches"):
        for attempt in range(max_retries):
            try:
                handle = Entrez.efetch(db="nucleotide", 
                                     rettype="gb", 
                                     retmode="text",
                                     retstart=start,
                                     retmax=batch_size,
                                     webenv=webenv,
                                     query_key=query_key)
                                     
                batch_records = SeqIO.parse(handle, "genbank")
                
                for record in batch_records:
                    # Store original header
                    original_header = record.description
                    record.original_header = original_header
                    
                    segment_type = get_segment_type(record)
                    sequences.append({
                        'id': record.id,
                        'record': record,
                        'segment': segment_type,
                        'original_header': original_header
                    })
                    
                    # Update counts
                    if segment_type:
                        segment_counts[segment_type] += 1
                    else:
                        segment_counts['Unknown'] += 1
                
                handle.close()
                break  # Success, exit retry loop
                
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    print(f"\nError downloading batch starting at {start}: {str(e)}")
                    print("Skipping this batch and continuing...")
                    continue
                print(f"\nRetry {attempt + 1} for batch starting at {start}...")
                time.sleep(retry_delay)
    return sequences, segment_counts, location_counts

def get_segment_from_protein(description):
    """Helper function to determine segment type from protein names in header"""
    description = description.lower()
    
    # S segment proteins
    s_proteins = ['nucleoprotein', 'glycoprotein', 'gpc', 'np']
    # L segment proteins
    l_proteins = ['polymerase', 'z protein', 'l protein']
    
    for protein in s_proteins:
        if protein in description:
            return 'S'
    for protein in l_proteins:
        if protein in description:
            return 'L'
    
    return None

def process_sequences(sequences, segment_type):
    """Process sequences based on segment type (L, S, or both)"""
    if segment_type.upper() == 'BOTH':
        l_sequences = []
        s_sequences = []
        unknown_sequences = []
        unknown_headers = []
        
        for seq in sequences:
            record = seq['record']
            original_header = seq['original_header']
            
            # First try the official segment annotation
            if seq['segment'] in ['L', 'S']:
                final_segment = seq['segment']
            else:
                # For unknown segments, try to determine from protein names
                final_segment = get_segment_from_protein(original_header)
            
            # Only modify header after classification is complete
            record.id = get_metadata(record)
            record.description = ''
            
            if final_segment == 'L':
                l_sequences.append(record)
            elif final_segment == 'S':
                s_sequences.append(record)
            else:
                unknown_sequences.append(record)
                unknown_headers.append(original_header)
                
        return l_sequences, s_sequences, unknown_sequences, unknown_headers
    else:
        filtered_sequences = []
        target_segment = segment_type.upper()
        
        for seq in sequences:
            record = seq['record']
            original_header = seq['original_header']
            
            # First try the official segment annotation
            if seq['segment'] == target_segment:
                final_segment = seq['segment']
            else:
                # For unknown segments, try to determine from protein names
                final_segment = get_segment_from_protein(original_header)
            
            if final_segment == target_segment:
                record.id = get_metadata(record)
                record.description = ''
                filtered_sequences.append(record)
                    
        return filtered_sequences

def calculate_location_counts(sequences):
    """Calculate location counts for each segment type"""
    locations = {'L': {}, 'S': {}, 'unknown': {}}
    
    for seq in sequences:
        record = seq['record']
        segment = get_segment_type(record)
        segment_type = 'unknown' if segment is None else segment
        
        location = "UnknownLoc"
        for feature in record.features:
            if feature.type == "source":
                if 'geo_loc_name' in feature.qualifiers:
                    geo_loc = feature.qualifiers['geo_loc_name'][0]
                    if 'missing' not in geo_loc.lower():
                        location = geo_loc.split(':')[0].strip()
                        location = get_standardized_country_name(location)
        
        if location not in locations[segment_type]:
            locations[segment_type][location] = 0
        locations[segment_type][location] += 1
    
    return locations

def write_summary(outdir, initial_total, filtered_total, initial_segment_counts, location_counts, requested_segment, written_counts, filtered_sequences, genome_choice, completeness=None, sequences=None, host_choice=None, completeness_filtered=None):
    """Write summary report to a file"""
    summary_file = os.path.join(outdir, "summary_Lassa.txt")
    
    with open(summary_file, 'w') as f:
        f.write("Lassa Virus Sequence Download Summary\n")
        f.write("====================================\n\n")
        
        # Document filtering steps
        write_filtering_steps(f, sequences, genome_choice, completeness, 
                            host_choice, completeness_filtered, filtered_sequences)
        
        # Remove Output Files section from here - it will be written after metadata filtering

def write_geographical_distribution(f, locations, title):
    """Helper function to write geographical distribution tables"""
    f.write(f"\n{title}:\n")
    f.write("-" * len(title) + "\n")
    f.write("Country        L segments    S segments    Unknown         Total\n")
    f.write("-----------   -----------   -----------   ---------   ----------\n")
    
    all_countries = set()
    for segment_type in ['L', 'S', 'unknown']:
        all_countries.update(locations[segment_type].keys())
    
    total_l = 0
    total_s = 0
    total_unknown = 0
    for country in sorted(all_countries):
        l_count = locations['L'].get(country, 0)
        s_count = locations['S'].get(country, 0)
        unknown_count = locations['unknown'].get(country, 0)
        country_total = l_count + s_count + unknown_count
        
        if country_total > 0:
            f.write(f"{country:<13} {l_count:>11}   {s_count:>11}   {unknown_count:>9}   {country_total:>10}\n")
        
        total_l += l_count
        total_s += s_count
        total_unknown += unknown_count
    
    f.write("-" * 60 + "\n")
    total_all = total_l + total_s + total_unknown
    f.write(f"{'Total':<13} {total_l:>11}   {total_s:>11}   {total_unknown:>9}   {total_all:>10}\n\n")

def get_user_input(prompt, valid_options):
    """Helper function to get valid user input"""
    while True:
        print(prompt)
        choice = input("Enter your choice: ").strip()
        if choice in valid_options:
            return choice
        print(f"Invalid choice. Please choose from {', '.join(valid_options)}")

def get_completeness():
    """Get valid completeness percentage"""
    while True:
        try:
            completeness = float(input("Enter minimum sequence completeness (1-100): "))
            if 1 <= completeness <= 100:
                return completeness
            print("Please enter a value between 1 and 100")
        except ValueError:
            print("Please enter a valid number")

def is_complete_sequence(record):
    """Check if sequence is complete based on length (>99% of reference)"""
    reference_lengths = {
        'L': 7279,  # Reference length for L segment
        'S': 3402   # Reference length for S segment
    }
    
    # Get segment type
    segment = get_segment_type(record)
    if not segment:
        return False
        
    # Calculate completeness percentage
    seq_length = len(record.seq)
    ref_length = reference_lengths[segment]
    completeness = (seq_length / ref_length) * 100
    
    # Consider sequence complete if it's at least 99% of the reference length
    return completeness >= 99

def meets_minimum_completeness(record, min_completeness):
    """Check if sequence meets minimum completeness percentage"""
    reference_lengths = {
        'L': 7279,  # Reference length for L segment
        'S': 3402   # Reference length for S segment
    }
    
    # Get segment type
    segment = get_segment_type(record)
    if not segment:
        return False
    
    # Calculate completeness
    seq_length = len(record.seq)
    ref_length = reference_lengths[segment]
    completeness = (seq_length / ref_length) * 100
    
    return completeness >= min_completeness

def calculate_segment_counts(sequences):
    """Calculate segment counts from a list of sequences"""
    counts = {'L': 0, 'S': 0, 'unknown': 0}
    for seq in sequences:
        segment = get_segment_type(seq['record'])
        if segment:
            counts[segment] += 1
        else:
            counts['unknown'] += 1
    return counts

def analyze_hosts(sequences):
    """Print all unique hosts found in sequences"""
    host_counts = {}
    no_host_count = 0
    
    for seq in sequences:
        record = seq['record']
        host_found = False
        
        for feature in record.features:
            if feature.type == "source":
                if 'host' in feature.qualifiers:
                    host = feature.qualifiers['host'][0].lower()
                    if host not in host_counts:
                        host_counts[host] = 0
                    host_counts[host] += 1
                    host_found = True
                    break
        
        if not host_found:
            no_host_count += 1
    
    print("\nHost distribution in sequences:")
    print("-----------------------------")
    for host, count in sorted(host_counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"{host}: {count} sequences")
    if no_host_count > 0:
        print(f"\nSequences with no host information: {no_host_count}")

def is_human_host(host):
    """Check if the host is human"""
    human_patterns = [
        'homo sapiens', 
        'human', 
        'homon sapiens',  # Common misspelling
        'h. sapiens',
        'humans',
        'homo sapien',    # Common misspelling
        'h sapiens',
        'human patient',
        'patient',
        'human isolate'
    ]
    return any(pattern in host.lower() for pattern in human_patterns)

def is_rodent_host(host):
    """Check if the host is a rodent"""
    rodent_patterns = [
        # Specific species
        'mastomys natalensis',
        'mastomys',
        'natal multimammate',
        'multimammate rat',
        'multimammate mouse',
        'hylomyscus pamfi',  # Added this species
        # Genera
        'mus',
        'rattus',
        'lophuromys',
        'praomys',
        'hylomyscus',  # Added genus
        # Common names
        'rodent',
        'mouse',
        'mice',
        'rat',
        # Scientific terms
        'natalensis',
        'murinae',
        'muridae'
    ]
    return any(pattern in host.lower() for pattern in rodent_patterns)

def write_host_distribution(f, sequences):
    """Write host distribution to summary file"""
    host_counts = {'human': 0, 'rodent': 0, 'other': 0, 'unknown': 0}
    other_hosts = set()
    
    for seq in sequences:
        record = seq['record']
        host_found = False
        
        for feature in record.features:
            if feature.type == "source" and 'host' in feature.qualifiers:
                host = feature.qualifiers['host'][0].lower()
                host_found = True
                
                if is_human_host(host):
                    host_counts['human'] += 1
                elif is_rodent_host(host):
                    host_counts['rodent'] += 1
                else:
                    host_counts['other'] += 1
                    other_hosts.add(host)
                break
        
        if not host_found:
            host_counts['unknown'] += 1
    
    f.write(f"Human hosts: {host_counts['human']}\n")
    f.write(f"Rodent hosts: {host_counts['rodent']}\n")
    f.write(f"Other hosts: {host_counts['other']}\n")
    f.write(f"Unknown hosts: {host_counts['unknown']}\n")
    
    if other_hosts:
        f.write("\nOther host types found:\n")
        for host in sorted(other_hosts):
            f.write(f"- {host}\n")
    f.write("\n")

def write_filtering_steps(f, sequences, genome_choice, completeness, host_choice, completeness_filtered, filtered_sequences):
    """Document the filtering steps and their impact"""
    f.write("\nFiltering Steps Summary\n")
    f.write("=====================\n\n")
    
    # Initial counts
    initial_counts = calculate_segment_counts(sequences)
    initial_locations = calculate_location_counts(sequences)
    
    f.write("1. Initial Dataset\n")
    f.write("----------------\n")
    f.write(f"Total sequences: {len(sequences)}\n")
    f.write(f"L segments: {initial_counts['L']}\n")
    f.write(f"S segments: {initial_counts['S']}\n")
    f.write(f"Unknown segments: {initial_counts['unknown']}\n\n")
    
    # Add detailed host information
    f.write("Initial Host Distribution\n")
    f.write("----------------------\n")
    host_counts = {}  # Dictionary to store counts for each unique host
    host_details = {'human': set(), 'rodent': set(), 'other': set()}
    no_host_count = 0
    
    for seq in sequences:
        record = seq['record']
        host_found = False
        
        for feature in record.features:
            if feature.type == "source" and 'host' in feature.qualifiers:
                host = feature.qualifiers['host'][0]
                host_found = True
                
                # Update count for this specific host
                if host not in host_counts:
                    host_counts[host] = 0
                host_counts[host] += 1
                
                if is_human_host(host):
                    host_details['human'].add(host.lower())
                elif is_rodent_host(host):
                    host_details['rodent'].add(host.lower())
                else:
                    host_details['other'].add(host.lower())
                break
        
        if not host_found:
            no_host_count += 1
    
    # Calculate totals for each category
    total_human = sum(host_counts[host] for host in host_counts if is_human_host(host))
    total_rodent = sum(host_counts[host] for host in host_counts if is_rodent_host(host))
    total_other = sum(host_counts[host] for host in host_counts 
                     if not is_human_host(host) and not is_rodent_host(host))
    
    # Write human hosts with counts
    f.write(f"\nHuman hosts found (Total: {total_human} sequences):\n")
    for host in sorted(host_details['human']):
        matching_hosts = [h for h in host_counts.keys() if h.lower() == host]
        for matching_host in matching_hosts:
            f.write(f"- {matching_host}: {host_counts[matching_host]} sequences\n")
    
    # Write rodent hosts with counts
    f.write(f"\nRodent hosts found (Total: {total_rodent} sequences):\n")
    for host in sorted(host_details['rodent']):
        matching_hosts = [h for h in host_counts.keys() if h.lower() == host]
        for matching_host in matching_hosts:
            f.write(f"- {matching_host}: {host_counts[matching_host]} sequences\n")
    
    # Write other hosts with counts
    if host_details['other']:
        f.write(f"\nOther hosts found (Total: {total_other} sequences):\n")
        for host in sorted(host_details['other']):
            matching_hosts = [h for h in host_counts.keys() if h.lower() == host]
            for matching_host in matching_hosts:
                f.write(f"- {matching_host}: {host_counts[matching_host]} sequences\n")
    
    f.write(f"\nSequences with no host information: {no_host_count}\n\n")
    
    write_geographical_distribution(f, initial_locations, "Initial Geographical Distribution")
    
    # Completeness filtering
    if genome_choice != '3':
        f.write("\n2. After Completeness Filtering\n")
        f.write("----------------------------\n")
        if genome_choice == '1':
            f.write("Applied filter: Complete genomes only (>99%)\n")
        else:
            f.write(f"Applied filter: Minimum completeness {completeness}%\n")
        
        completeness_counts = calculate_segment_counts(completeness_filtered)
        completeness_locations = calculate_location_counts(completeness_filtered)
        
        f.write(f"\nRemaining sequences: {len(completeness_filtered)}\n")
        f.write(f"L segments: {completeness_counts['L']}\n")
        f.write(f"S segments: {completeness_counts['S']}\n")
        f.write(f"Unknown segments: {completeness_counts['unknown']}\n\n")
        write_geographical_distribution(f, completeness_locations, "Geographical Distribution After Completeness Filter")
    
    # Host filtering
    if host_choice != '4':
        f.write("\n3. After Host Filtering\n")
        f.write("---------------------\n")
        host_type = {
            '1': 'Human only',
            '2': 'Rodent only',
            '3': 'Human and Rodent'
        }[host_choice]
        f.write(f"Applied filter: {host_type}\n")
        
        final_counts = calculate_segment_counts(filtered_sequences)
        final_locations = calculate_location_counts(filtered_sequences)
        
        f.write(f"\nFinal sequences: {len(filtered_sequences)}\n")
        f.write(f"L segments: {final_counts['L']}\n")
        f.write(f"S segments: {final_counts['S']}\n")
        f.write(f"Unknown segments: {final_counts['unknown']}\n\n")
        write_geographical_distribution(f, final_locations, "Final Geographical Distribution")

def filter_by_host(sequences, host_choice):
    """Filter sequences based on host"""
    filtered_sequences = []
    
    for seq in sequences:
        record = seq['record']
        include_sequence = False
        host_found = False
        
        for feature in record.features:
            if feature.type == "source" and 'host' in feature.qualifiers:
                host_found = True
                host = feature.qualifiers['host'][0].lower()
                
                if host_choice == '1':  # Human only
                    include_sequence = is_human_host(host)
                elif host_choice == '2':  # Rodent only
                    include_sequence = is_rodent_host(host)
                elif host_choice == '3':  # Both human and rodent
                    include_sequence = is_human_host(host) or is_rodent_host(host)
                elif host_choice == '4':  # No filter
                    include_sequence = True
                break
        
        if host_choice == '4' or include_sequence:
            filtered_sequences.append(seq)
    
    return filtered_sequences

def filter_by_metadata(sequences, metadata_choice):
    """Filter sequences based on metadata completeness"""
    filtered_sequences = []
    
    for seq in sequences:
        record = seq['record']
        metadata = get_metadata(record)  # This gives us accession_location_date
        
        include_sequence = True
        if metadata_choice == '1':  # Known location only
            if 'UnknownLoc' in metadata:
                include_sequence = False
        elif metadata_choice == '2':  # Known date only
            if 'UnknownDate' in metadata:
                include_sequence = False
        elif metadata_choice == '3':  # Both known
            if 'UnknownLoc' in metadata or 'UnknownDate' in metadata:
                include_sequence = False
        # metadata_choice == '4' means no filter, include all sequences
        
        if include_sequence:
            filtered_sequences.append(seq)
    
    return filtered_sequences

def filter_by_country(sequences, countries):
    """Filter sequences based on specified countries"""
    if not countries:  # If no countries specified, return all sequences
        return sequences
        
    filtered_sequences = []
    # Convert input countries to standardized format
    standardized_countries = [get_standardized_country_name(c) for c in countries]
    
    for seq in sequences:
        record = seq['record']
        include_sequence = False
        
        for feature in record.features:
            if feature.type == "source" and 'geo_loc_name' in feature.qualifiers:
                location = feature.qualifiers['geo_loc_name'][0]
                if 'missing' not in location.lower():
                    country = location.split(':')[0].strip()
                    standardized_country = get_standardized_country_name(country)
                    if standardized_country in standardized_countries:
                        include_sequence = True
                        break
        
        if include_sequence:
            filtered_sequences.append(seq)
    
    return filtered_sequences

def write_metadata_filtering_summary(f, sequences, metadata_filtered_sequences, metadata_choice, written_counts):
    """Write metadata filtering summary to the report"""
    # Only write metadata filtering summary if actual filtering was applied
    if metadata_choice != '4':
        f.write("\n4. After Metadata Filtering\n")
        f.write("------------------------\n")
        
        # Add description of applied filter
        filter_descriptions = {
            '1': 'Applied filter: Known location only',
            '2': 'Applied filter: Known date only',
            '3': 'Applied filter: Both known location and date'
        }
        f.write(f"{filter_descriptions[metadata_choice]}\n")
        
        # Count remaining sequences after filtering
        final_counts = calculate_segment_counts(metadata_filtered_sequences)
        final_locations = calculate_location_counts(metadata_filtered_sequences)
        
        f.write(f"\nAfter metadata filtering:\n")
        f.write(f"Final sequences: {len(metadata_filtered_sequences)}\n")
        f.write(f"L segments: {final_counts['L']}\n")
        f.write(f"S segments: {final_counts['S']}\n")
        f.write(f"Unknown segments: {final_counts['unknown']}\n\n")
        
        write_geographical_distribution(f, final_locations, "Final Geographical Distribution After Metadata Filter")

def write_country_filtering_summary(f, sequences, country_filtered_sequences, countries, written_counts):
    """Write country filtering summary and final output files section"""
    if countries:  # Only write if country filtering was applied
        f.write("\n5. After Country Filtering\n")
        f.write("----------------------\n")
        f.write(f"Applied filter: Selected countries: {countries}\n")
        
        final_counts = calculate_segment_counts(country_filtered_sequences)
        final_locations = calculate_location_counts(country_filtered_sequences)
        
        f.write(f"\nAfter country filtering:\n")
        f.write(f"Final sequences: {len(country_filtered_sequences)}\n")
        f.write(f"L segments: {final_counts['L']}\n")
        f.write(f"S segments: {final_counts['S']}\n")
        f.write(f"Unknown segments: {final_counts['unknown']}\n\n")
        
        write_geographical_distribution(f, final_locations, "Final Geographical Distribution After Country Filter")
    
    # Always write the Output Files section at the very end
    f.write("\nOutput Files\n")
    f.write("------------\n")
    f.write(f"L segments: FASTA/L_segment/lassa_l_segments.fasta ({written_counts['L']} sequences)\n")
    f.write(f"S segments: FASTA/S_segment/lassa_s_segments.fasta ({written_counts['S']} sequences)\n")
    if written_counts['unknown'] > 0:
        f.write(f"Unknown segments: FASTA/unknown_segment/lassa_unknown_segments.fasta ({written_counts['unknown']} sequences)\n")

def cli_main():
    try:
        class CustomFormatter(argparse.RawDescriptionHelpFormatter):
            def _split_lines(self, text, width):
                if text.startswith('Output directory') or \
                   text.startswith('Minimum sequence') or \
                   text.startswith('Genome completeness') or \
                   text.startswith('Host filter') or \
                   text.startswith('Metadata completeness') or \
                   text.startswith('Comma-separated list') or \
                   text.startswith('(Optional) File'):
                    return text.splitlines()
                return argparse.RawDescriptionHelpFormatter._split_lines(self, text, width)

        parser = argparse.ArgumentParser(
            description='Download and filter Lassa virus sequences',
            epilog='''example:
  # Download complete genomes from human hosts with known location and date from multiple countries:
  lassaseq -o lassa_output --genome 1 --host 1 --metadata 3 --countries "Sierra Leone, Guinea"''',
            formatter_class=CustomFormatter)
        
        parser.add_argument('-o', '--outdir', required=True, metavar='',
                          help='''Output directory for sequences''')
        
        parser.add_argument('--genome', choices=['1', '2', '3'],
                          help='''Genome completeness filter:
1 = Complete genomes only (>99 percent of reference length)
2 = Partial genomes (specify minimum percent with --completeness)
3 = No completeness filter''')
        
        parser.add_argument('--completeness', type=float, metavar='',
                          help='''Minimum sequence completeness (1-100 percent)
Required when --genome=2''')
        
        parser.add_argument('--host', choices=['1', '2', '3', '4'],
                          help='''Host filter:
1 = Human sequences only
2 = Rodent sequences only
3 = Both human and rodent sequences
4 = No host filter''')
        
        parser.add_argument('--metadata', choices=['1', '2', '3', '4'],
                          help='''Metadata completeness filter:
1 = Keep only sequences with known location
2 = Keep only sequences with known date
3 = Keep only sequences with both known location and date
4 = No metadata filter''')
        
        parser.add_argument('--countries', type=str, metavar='',
                          help='''Comma-separated list of countries to filter sequences
Examples: "Sierra Leone, Guinea" or "Nigeria, Mali"
Available: Nigeria, Sierra Leone, Liberia, Guinea, Mali,
          Ghana, Benin, Burkina Faso, Ivory Coast, Togo''')
        
        parser.add_argument('--remove', type=str, metavar='',
                          help='''(Optional) File containing accession numbers to remove
One accession number per line, lines starting with # are ignored''')
        
        args = parser.parse_args()
        
        # Initialize countries as None if not provided
        countries = None
        if args.countries:
            countries = [country.strip() for country in args.countries.split(',')]
        
        # Interactive mode if optional arguments are not provided
        if not args.genome:
            args.genome = get_user_input(
                "\nSelect genome completeness filter:\n"
                "1 = Complete genomes only (>99 percent)\n"
                "2 = Partial genomes (specify minimum percent)\n"
                "3 = No completeness filter",
                ['1', '2', '3'])
            
            if args.genome == '2' and not args.completeness:
                args.completeness = get_completeness()
        
        if not args.host:
            args.host = get_user_input(
                "\nSelect host filter:\n"
                "1 = Human sequences only\n"
                "2 = Rodent sequences only\n"
                "3 = Both human and rodent sequences\n"
                "4 = No host filter",
                ['1', '2', '3', '4'])
        
        if not args.metadata:
            args.metadata = get_user_input(
                "\nSelect metadata completeness filter:\n"
                "1 = Keep only sequences with known location\n"
                "2 = Keep only sequences with known date\n"
                "3 = Keep only sequences with both known location and date\n"
                "4 = No metadata filter",
                ['1', '2', '3', '4'])
        
        # Continue with the rest of the code...
        print("\nStarting Lassa virus sequence download")
        print(f"Output directory: {args.outdir}")
        
        # Create output directories
        fasta_dir = os.path.join(args.outdir, "FASTA")
        l_segment_dir = os.path.join(fasta_dir, "L_segment")
        s_segment_dir = os.path.join(fasta_dir, "S_segment")
        unknown_segment_dir = os.path.join(fasta_dir, "unknown_segment")
        
        for directory in [fasta_dir, l_segment_dir, s_segment_dir, unknown_segment_dir]:
            os.makedirs(directory, exist_ok=True)

        # Download sequences
        sequences, segment_counts, location_counts = fetch_sequences()
        initial_total = len(sequences)
        initial_segment_counts = calculate_segment_counts(sequences)

        # After downloading sequences but before filtering, remove specified sequences
        if args.remove and os.path.exists(args.remove):
            with open(args.remove) as f:
                # Read accessions to remove, skip comments and empty lines
                remove_accessions = {line.strip() for line in f 
                                  if line.strip() and not line.startswith('#')}
                
            # Filter out sequences with matching accessions
            original_count = len(sequences)
            sequences = [seq for seq in sequences 
                       if seq['record'].id not in remove_accessions]
            removed_count = original_count - len(sequences)
            
            print(f"\nRemoved {removed_count} sequences based on remove.txt")

        # Apply all filters in sequence
        if args.genome != '3':  # Apply completeness filter if requested
            completeness_filtered = []
            for seq in sequences:
                if args.genome == '1' and is_complete_sequence(seq['record']):
                    completeness_filtered.append(seq)
                elif args.genome == '2' and meets_minimum_completeness(seq['record'], args.completeness):
                    completeness_filtered.append(seq)
        else:
            completeness_filtered = sequences

        # Apply remaining filters
        host_filtered = filter_by_host(completeness_filtered, args.host)
        metadata_filtered = filter_by_metadata(host_filtered, args.metadata)
        
        # Process country filtering
        if countries:
            final_filtered = filter_by_country(metadata_filtered, countries)
        else:
            final_filtered = metadata_filtered

        # Process final filtered sequences and write FASTA files
        l_sequences, s_sequences, unknown_sequences, unknown_headers = process_sequences(final_filtered, 'both')
        
        # Write FASTA files with final filtered sequences
        l_output = os.path.join(l_segment_dir, "lassa_l_segments.fasta")
        s_output = os.path.join(s_segment_dir, "lassa_s_segments.fasta")
        unknown_output = os.path.join(unknown_segment_dir, "lassa_unknown_segments.fasta")
        
        SeqIO.write(l_sequences, l_output, "fasta")
        SeqIO.write(s_sequences, s_output, "fasta")
        SeqIO.write(unknown_sequences, unknown_output, "fasta")
        
        written_counts = {
            'L': len(l_sequences),
            'S': len(s_sequences),
            'unknown': len(unknown_sequences)
        }

        # Write summary file
        write_summary(args.outdir, initial_total, len(host_filtered), 
                     initial_segment_counts, location_counts, 'both', 
                     written_counts, host_filtered, args.genome, 
                     args.completeness, sequences, args.host, completeness_filtered)
        
        # Append metadata and country filtering results
        with open(os.path.join(args.outdir, 'summary_Lassa.txt'), 'a') as f:
            write_metadata_filtering_summary(f, host_filtered, metadata_filtered, args.metadata, written_counts)
            write_country_filtering_summary(f, metadata_filtered, final_filtered, countries, written_counts)

        print(f"\nFinal counts after all filtering:")
        print(f"Wrote {written_counts['L']} L segments, {written_counts['S']} S segments, "
              f"and {written_counts['unknown']} unknown segments")
        print(f"Updated summary report written to: {os.path.join(args.outdir, 'summary_Lassa.txt')}")

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    cli_main() 