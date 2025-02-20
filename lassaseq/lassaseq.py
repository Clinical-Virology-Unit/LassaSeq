from Bio import Entrez
from Bio import SeqIO
from tqdm import tqdm
import argparse
import os
from datetime import datetime
import calendar

def get_segment_type(record):
    """Helper function to determine segment type from various GenBank fields"""
    for feature in record.features:
        if feature.type == "source":
            if 'segment' in feature.qualifiers:
                segment_value = feature.qualifiers['segment'][0].upper()
                if segment_value in ['L', 'S']:
                    return segment_value
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

def clean_country_name(country):
    """Clean country name to remove spaces and special characters"""
    # Dictionary for specific country name fixes
    country_fixes = {
        'Sierra Leone': 'SierraLeone',
        'Burkina Faso': 'BurkinaFaso',
        'Costa Rica': 'CostaRica',
        'South Africa': 'SouthAfrica',
        "Cote d'Ivoire": 'IvoryCoast',
        "Côte d'Ivoire": 'IvoryCoast',
        'Ivory Coast': 'IvoryCoast'
        # Add more multi-word countries as needed
    }
    
    # Check if country is in our fixes dictionary
    if country in country_fixes:
        return country_fixes[country]
    
    # Otherwise, remove spaces and special characters
    return country.replace(' ', '').replace('-', '').replace(',', '')

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
                    location = clean_country_name(location)
            
            # Get collection date
            if 'collection_date' in feature.qualifiers:
                date_str = feature.qualifiers['collection_date'][0]
                if date_str.lower() != 'missing':
                    collection_date = convert_date_to_decimal_year(date_str)
    
    return f"{accession}_{location}_{collection_date}"

def fetch_sequences():
    Entrez.email = "anonymous@example.com"
    
    print("Searching for Lassa virus sequences...")
    search_term = "Mammarenavirus lassaense[Organism]"
    
    handle = Entrez.esearch(db="nucleotide", term=search_term, usehistory="y")
    record = Entrez.read(handle)
    handle.close()
    
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
                segment_type = get_segment_type(record)
                # Add sequence regardless of segment type
                sequences.append({
                    'id': record.id,
                    'record': record,
                    'segment': segment_type  # This will be None for unknown segments
                })
                
                # Update counts
                if segment_type:
                    segment_counts[segment_type] += 1
                    
                    # Get location and update location counts only for known segments
                    location = "UnknownLoc"
                    for feature in record.features:
                        if feature.type == "source":
                            if 'geo_loc_name' in feature.qualifiers:
                                geo_loc = feature.qualifiers['geo_loc_name'][0]
                                if 'missing' not in geo_loc.lower():
                                    location = geo_loc.split(':')[0].strip()
                                    location = clean_country_name(location)
                    
                    if location not in location_counts[segment_type]:
                        location_counts[segment_type][location] = 0
                    location_counts[segment_type][location] += 1
                else:
                    segment_counts['Unknown'] += 1
            
            handle.close()
            
        except Exception as e:
            print(f"Error downloading batch starting at {start}: {str(e)}")
            continue
    
    return sequences, segment_counts, location_counts

def process_sequences(sequences, segment_type):
    """Process sequences based on segment type (L, S, or both)"""
    if segment_type.upper() == 'BOTH':
        l_sequences = []
        s_sequences = []
        unknown_sequences = []
        unknown_headers = []  # New list to store original headers
        
        for seq in sequences:
            record = seq['record']
            # Store original header for unknown segments
            if seq['segment'] is None:
                unknown_headers.append(f">{record.id} {record.description}")
            
            record.id = get_metadata(record)
            record.description = ''  # Clear description to avoid duplication
            
            if seq['segment'] == 'L':
                l_sequences.append(record)
            elif seq['segment'] == 'S':
                s_sequences.append(record)
            elif seq['segment'] is None:
                unknown_sequences.append(record)
                
        return l_sequences, s_sequences, unknown_sequences, unknown_headers
    else:
        filtered_sequences = []
        unknown_sequences = []
        unknown_headers = []  # New list to store original headers
        
        for seq in sequences:
            record = seq['record']
            # Store original header for unknown segments
            if seq['segment'] is None:
                unknown_headers.append(f">{record.id} {record.description}")
            
            record.id = get_metadata(record)
            record.description = ''
            
            if seq['segment'] == segment_type.upper():
                filtered_sequences.append(record)
            elif seq['segment'] is None:
                unknown_sequences.append(record)
                
        return filtered_sequences, unknown_sequences, unknown_headers

def write_summary(outdir, total_count, segment_counts, location_counts, segment_type, written_counts, sequences):
    """Write summary report to a file"""
    summary_file = os.path.join(outdir, "lassa_download_summary.txt")
    
    # First, calculate unknown segment counts by location
    unknown_locations = {}
    for seq in sequences:
        if seq['segment'] is None:
            location = "UnknownLoc"
            for feature in seq['record'].features:
                if feature.type == "source":
                    if 'geo_loc_name' in feature.qualifiers:
                        geo_loc = feature.qualifiers['geo_loc_name'][0]
                        if 'missing' not in geo_loc.lower():
                            location = geo_loc.split(':')[0].strip()
                            location = clean_country_name(location)
            if location not in unknown_locations:
                unknown_locations[location] = 0
            unknown_locations[location] += 1
    
    with open(summary_file, 'w') as f:
        f.write("Lassa Virus Sequence Download Summary\n")
        f.write("====================================\n\n")
        f.write(f"Total Lassa virus sequences found: {total_count}\n")
        f.write(f"Segments found in database:\n")
        f.write(f"  L segments: {segment_counts['L']}\n")
        f.write(f"  S segments: {segment_counts['S']}\n")
        f.write(f"  Unknown/unspecified: {segment_counts['Unknown']}\n\n")
        
        f.write("Geographical Distribution of Segments:\n")
        f.write("-------------------------------------\n")
        f.write("Country      L segments  S segments  Unknown       Total\n")
        f.write("---------   ----------  ----------  -------    --------\n")
        
        # Get all unique countries
        all_countries = set(location_counts['L'].keys()) | set(location_counts['S'].keys()) | set(unknown_locations.keys())
        
        # Calculate and write counts for each country
        total_l = 0
        total_s = 0
        total_unknown = 0
        for country in sorted(all_countries):
            l_count = location_counts['L'].get(country, 0)
            s_count = location_counts['S'].get(country, 0)
            unknown_count = unknown_locations.get(country, 0)
            country_total = l_count + s_count + unknown_count
            f.write(f"{country:<12} {l_count:>10}  {s_count:>10}  {unknown_count:>7}    {country_total:>8}\n")
            total_l += l_count
            total_s += s_count
            total_unknown += unknown_count
        
        # Write totals
        f.write("-" * 52 + "\n")
        total_all = total_l + total_s + total_unknown
        f.write(f"{'Total':<12} {total_l:>10}  {total_s:>10}  {total_unknown:>7}    {total_all:>8}\n\n")
        
        f.write("Sequences downloaded:\n")
        if segment_type.upper() == 'BOTH':
            f.write(f"  L segments written: {written_counts['L']}\n")
            f.write(f"  S segments written: {written_counts['S']}\n")
            f.write(f"  Unknown segments written: {written_counts['unknown']}\n")
            f.write(f"Output files:\n")
            f.write(f"  L segments: lassa_l_segments.fasta\n")
            f.write(f"  S segments: lassa_s_segments.fasta\n")
            f.write(f"  Unknown segments: lassa_unknown_segments.fasta\n")
        else:
            f.write(f"  {segment_type.upper()} segments written: {written_counts['segment']}\n")
            f.write(f"  Unknown segments written: {written_counts['unknown']}\n")
            f.write(f"Output files:\n")
            f.write(f"  {segment_type.upper()} segments: lassa_{segment_type.lower()}_segments.fasta\n")
            f.write(f"  Unknown segments: lassa_unknown_segments.fasta\n")

def cli_main():
    parser = argparse.ArgumentParser(description='Download Lassa virus sequences')
    parser.add_argument('-o', '--outdir', required=True, help='Output directory for sequences')
    parser.add_argument('-s', '--segment', required=True, choices=['L', 'S', 'both'], 
                       help='Segment type to download (L, S, or both)')
    args = parser.parse_args()
    
    print(f"\nStarting Lassa virus sequence download for {args.segment} segment(s)")
    print(f"Output directory: {args.outdir}")
    
    os.makedirs(args.outdir, exist_ok=True)
    
    sequences, segment_counts, location_counts = fetch_sequences()
    
    if args.segment.upper() == 'BOTH':
        l_sequences, s_sequences, unknown_sequences, unknown_headers = process_sequences(sequences, args.segment)
        
        # Write L segments
        l_output = os.path.join(args.outdir, "lassa_l_segments.fasta")
        SeqIO.write(l_sequences, l_output, "fasta")
        
        # Write S segments
        s_output = os.path.join(args.outdir, "lassa_s_segments.fasta")
        SeqIO.write(s_sequences, s_output, "fasta")
        
        # Write unknown segments
        unknown_output = os.path.join(args.outdir, "lassa_unknown_segments.fasta")
        SeqIO.write(unknown_sequences, unknown_output, "fasta")
        
        # Write unknown headers
        unknown_headers_output = os.path.join(args.outdir, "unknown_segments_headers.txt")
        with open(unknown_headers_output, 'w') as f:
            f.write('\n'.join(unknown_headers))
        
        written_counts = {
            'L': len(l_sequences), 
            'S': len(s_sequences),
            'unknown': len(unknown_sequences)
        }
        print(f"\nWrote {len(l_sequences)} L segments, {len(s_sequences)} S segments, and {len(unknown_sequences)} unknown segments")
        print(f"Unknown segment headers written to: {unknown_headers_output}")
    else:
        filtered_sequences, unknown_sequences, unknown_headers = process_sequences(sequences, args.segment)
        output_file = os.path.join(args.outdir, f"lassa_{args.segment.lower()}_segments.fasta")
        SeqIO.write(filtered_sequences, output_file, "fasta")
        
        # Write unknown segments
        unknown_output = os.path.join(args.outdir, "lassa_unknown_segments.fasta")
        SeqIO.write(unknown_sequences, unknown_output, "fasta")
        
        # Write unknown headers
        unknown_headers_output = os.path.join(args.outdir, "unknown_segments_headers.txt")
        with open(unknown_headers_output, 'w') as f:
            f.write('\n'.join(unknown_headers))
        
        written_counts = {
            'segment': len(filtered_sequences),
            'unknown': len(unknown_sequences)
        }
        print(f"\nWrote {len(filtered_sequences)} {args.segment} segments and {len(unknown_sequences)} unknown segments")
        print(f"Unknown segment headers written to: {unknown_headers_output}")
    
    # Write summary report
    write_summary(args.outdir, len(sequences), segment_counts, location_counts, args.segment, written_counts, sequences)
    print(f"Summary report written to: {os.path.join(args.outdir, 'lassa_download_summary.txt')}")

if __name__ == "__main__":
    cli_main() 