from env import get_connection
import os
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split

def acquire_zillow() -> pd.DataFrame:
    '''
    acquire_zillow will use a local env.py
    using pre-set credentials called user, password, and host
    please make sure you have a properly formatted env.py
    file in the same directory as this module
    and that you have the access rights to mall_customers schema
    
    return: a single pandas dataframe
    '''
    if os.path.exists('zillow_data.csv'):
        df = pd.read_csv('zillow_data.csv')
    else:
        query ='''
        -- here, I want to ensure that I am selecting
        -- properties that have a transaction in 2017,
        -- the most recent version of those properties
        -- from there, I want to get the logerror for the zestimate
        -- and any potential supplementary information 
        -- available in the other tables
        -- SELECT: everything from properties aliased as prop
        SELECT prop.*,
        -- predictions_2017 : logerror and transactiondate
        predictions_2017.logerror,
        predictions_2017.transactiondate,
        -- all the other supplementary stuff
        air.airconditioningdesc,
        arch.architecturalstyledesc,
        build.buildingclassdesc,
        heat.heatingorsystemdesc,
        land.propertylandusedesc,
        story.storydesc,
        type.typeconstructiondesc
        FROM properties_2017 prop
        JOIN (
            SELECT parcelid, MAX(transactiondate) AS max_transactiondate
            FROM predictions_2017
            GROUP BY parcelid
            ) pred USING(parcelid)
        JOIN predictions_2017 ON pred.parcelid = predictions_2017.parcelid
                          AND pred.max_transactiondate = predictions_2017.transactiondate
        LEFT JOIN airconditioningtype air USING(airconditioningtypeid)
        LEFT JOIN architecturalstyletype arch USING(architecturalstyletypeid)
        LEFT JOIN buildingclasstype build USING(buildingclasstypeid)
        LEFT JOIN heatingorsystemtype heat USING(heatingorsystemtypeid)
        LEFT JOIN propertylandusetype land USING(propertylandusetypeid)
        LEFT JOIN storytype story USING(storytypeid)
        LEFT JOIN typeconstructiontype type USING(typeconstructiontypeid)
        WHERE propertylandusedesc = "Single Family Residential"
            AND transactiondate <= '2017-12-31'
            AND prop.longitude IS NOT NULL
            AND prop.latitude IS NOT NULL
        '''
        url = get_connection('zillow')
        df = pd.read_sql(query, url)
        df.to_csv('zillow_data.csv', index=False)
    return df

def missing_by_col(df): 
    '''
    returns a single series of null values by column name
    '''
    return df.isnull().sum(axis=0)

def missing_by_row(df) -> pd.DataFrame:
    '''
    prints out a report of how many rows have a certain
    number of columns/fields missing both by count and proportion
    
    '''
    count_missing = df.isnull().sum(axis=1)
    percent_missing = round((df.isnull().sum(axis=1) / df.shape[1]) * 100)
    rows_df = pd.DataFrame({
    'num_cols_missing': count_missing,
    'percent_cols_missing': percent_missing
    }).reset_index()\
    .groupby(['num_cols_missing', 'percent_cols_missing']).\
    count().reset_index().rename(columns={'index':'num_rows'})
    return rows_df

def get_fences(df, col, k=1.5) -> (float, float):
    '''
    get fences will calculate the upper and lower fence
    based on the inner quartile range of a single Series
    
    return: lower_bound and upper_bound, two floats
    '''
    # df.describe['.75']
    q3 = df[col].quantile(0.75)
    q1 = df[col].quantile(0.25)
    iqr = q3 - q1
    upper_bound = q3 + (k * iqr)
    lower_bound = q1 - (k * iqr)
    return lower_bound, upper_bound

def report_outliers(df, k=1.5) -> None:
    '''
    report_outliers will print a subset of each continuous
    series in a dataframe (based on numeric quality and n>20)
    and will print out results of this analysis with the fences
    in places
    '''
    num_df = df.select_dtypes('number')
    for col in num_df:
        if len(num_df[col].value_counts()) > 20:
            lower_bound, upper_bound = get_fences(df,col, k=k)
            print(f'Outliers for Col {col}:')
            print('lower: ', lower_bound, 'upper: ', upper_bound)
            print(df[col][(
                df[col] > upper_bound) | (df[col] < lower_bound)])
            print('----------')


def summarize(df, k=1.5) -> None:
    '''
    Summarize will take in a pandas DataFrame
    and print summary statistics:
    
    info
    shape
    outliers
    description
    missing data stats
    
    return: None (prints to console)
    '''
    # print info on the df
    print('Shape of Data: ')
    print(df.shape)
    print('======================\n======================')
    print('Info: ')
    print(df.info())
    print('======================\n======================')
    print('Descriptions:')
    # print the description of the df, transpose, output markdown
    print(df.describe().T.to_markdown())
    print('======================\n======================')
    # lets do that for categorical info as well
    # we will use select_dtypes to look at just Objects
    print(df.select_dtypes('O').describe().T.to_markdown())
    print('======================\n======================')
    print('missing values:')
    print('by column:')
    print(missing_by_col(df).to_markdown())
    print('by row: ')
    print(missing_by_row(df).to_markdown())
    print('======================\n======================')
    print('Outliers: ')
    print(report_outliers(df, k=k))
    print('======================\n======================')

def split_data(df, target=None) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    '''
    split_data will split data into train, validate, and test sets
    
    if a discrete target is in the data set, it may be specified
    with the target kwarg (Default None)
    
    return: three pandas DataFrames
    '''
    train_val, test = train_test_split(
        df, 
        train_size=0.8, 
        random_state=1349,
        stratify=target)
    train, validate = train_test_split(
        train_val,
        train_size=0.7,
        random_state=1349,
        stratify=target)
    return train, validate, test

def get_continuous_feats(df) -> list:
    '''
    find all continuous numerical features
    
    return: list of column names (strings)
    '''
    num_cols = []
    num_df = df.select_dtypes('number')
    for col in num_df:
        if num_df[col].nunique() > 20:
            num_cols.append(col)
    return num_cols

def handle_missing_values(df, 
                          prop_required_column, 
                          prop_required_row):
    '''
    Utilizing an input proportion for the column and rows of DataFrame df,
    drop the missing values per the axis contingent on the amount of data present.
    '''
    prop_missing_column = 1 - prop_required_column 
    # multiply the axis with with the appropriate ratio
    # this will return the number of rows that we want to reference
    # for our dropna function
    n_required_column = round(df.shape[0] * prop_required_column)
    df = df.dropna(axis=1, thresh=n_required_column)
    n_required_row = round(df.shape[1] * prop_required_row)
    df = df.dropna(axis=0, thresh=n_required_row)
    return df

def prep_zillow(
    df, 
    prop_required_row=0.75, 
    prop_required_column=0.75
    ) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    '''
    prep mall will set the index of the customer id to the 
    dataframe index, and will  scale continuous data in the df.
    
    return: a single, cleaned dataset.
    '''
    df = handle_missing_values(
        df, 
        prop_required_column=prop_required_column,
        prop_required_row=prop_required_row
    )
    # take care of any duplicates:
    df = df.drop_duplicates()
    train, validate, test = split_data(df)
    num_cols = get_continuous_feats(df)
    # preprocessing:
    #make a scaler:
    scaler = MinMaxScaler()
    scaled_cols = [col + '_scaled' for col in num_cols]
    train[scaled_cols] = scaler.fit_transform(train[num_cols])
    validate[scaled_cols] = scaler.transform(validate[num_cols])
    test[scaled_cols] = scaler.transform(test[num_cols])
    return train, validate, test

def wrangle_zillow(summarization=True,
                   k=1.5,
                   prop_required_column=0.75,
                   prop_required_row=0.75) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    '''
    wrangle_zillow will acquire and prepare zillow data
    
    if summarization is set to True, a console report 
    of data summary will be output to the console.
    
    return: train, validate, and test data sets with scaled numeric information
    '''
    if summarization:
        summarize(acquire_zillow(), k=k)
    train, validate, test = prep_zillow(
        acquire_zillow(),
        prop_required_column=prop_required_column,
        prop_required_row=prop_required_row
    )
    return train, validate, test