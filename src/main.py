'''
Main.py

Executes all the code for Problem 8 of the 2026 MinneMUDAC 
Data science competition

1. Get clean preprocessed data
2. Run Monte Carlo simulation for shelf locations
3. Calculate capacity-weighted E2SFCA access score across draws
4. Compute statistics to compare E2SFCA by LILA status
5. Perform spatial analysis by
    a) Using Gi* to find hot/cold spots of E2SFCA
    b) Calculating spearman correlation of E2SFCA and retail access
    c) Performing Bivariate Local Moran's I of retail access and E2SFCA
    d) Creating 2x2 quadrat classification (low/high retail x low/high food shelf)
6. Construct Visualizations
'''


from preprocess import get_data
from shelf_location import get_locations
from shelf_scores import get_scores
from shelf_statistics import get_statistics
from spatial_analysis import *
from visuals import *


def main():
    '''
    Runs the full pipeline from raw data to spatial analysis.
    '''

    # Step 1: Get clean preprocessed data
    get_data()

    # Step 2: Run Monte Carlo simulation for shelf locations
    get_locations()
    
    #Step 3: Calculate capacity-weighted E2SFCA access score across draws
    get_scores()
    
    #Step 4: Compute statistics to compare E2SFCA by LILA status
    get_statistics()
    
    #Step 5: Perform Spatial Analysis
    run_gistar() 
    run_spearman() 
    run_bivariate_moran()
    run_quadrat()
    
    #Step 6: Construct Visualizations
    generate_all_visuals()
    

if __name__ == "__main__":
    main()