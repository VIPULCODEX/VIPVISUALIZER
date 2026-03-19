import pandas as pd

data = {
    'PairID': ['P1', 'P2', 'P3', 'P4'],
    'DonorBloodGroup': ['A', 'B', 'O', 'B'],
    'RecipientBloodGroup': ['B', 'O', 'A', 'A']
}

df = pd.DataFrame(data)
df.to_excel('sample_nodes.xlsx', index=False)
print("Created sample_nodes.xlsx")
