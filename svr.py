import numpy as np
import matplotlib.pyplot as plt
import sklearn
import pandas as pd

from sklearn.svm import SVR
#from sklearn.preprocessing import StandardScaler

X = np.sort(5 * np.random.rand(40, 1), axis=0)
y1 = np.sin(X).ravel()
y2 = np.sin(X).ravel()
y3 = np.sin(X).ravel()
y4 = np.sin(X).ravel()
y5 = np.sin(X).ravel()

y1[::5] += 3 * (0.5 - np.random.rand(8))
y2[::5] += 3 * (0.5 - np.random.rand(8))
y3[::5] += 3 * (0.5 - np.random.rand(8))
y4[::5] += 3 * (0.5 - np.random.rand(8))
y5[::5] += 3 * (0.5 - np.random.rand(8))

y = np.concatenate((y1, y2, y3, y4, y5))
X = np.concatenate((X, X, X, X, X))

#y1 = y[::5] + 3 * (0.5 - np.random.rand(8))
#y2 = y[::5] + 3 * (0.5 - np.random.rand(8))
#y3 = y[::5] + 3 * (0.5 - np.random.rand(8))
#y4 = y[::5] + 3 * (0.5 - np.random.rand(8))
#y5 = y[::5] + 3 * (0.5 - np.random.rand(8))

#y = y1
#sc_X = StandardScaler()
#sc_y = StandardScaler()
#X = sc_X.fit_transform(X)
#y = sc_y.fit_transform(y)

regressor = SVR(kernel = 'rbf')
regressor.fit(X, y)

y_pred = regressor.predict([[2.5]])
print(y_pred)
y_pred = regressor.predict([[2.5]])
print(y_pred)
y_pred = regressor.predict([[2.5]])
print(y_pred)
#y_pred = sc_y.inverse_transform(y_pred)

X_grid = np.arange(min(X), max(X), 0.01) #this step required because data is feature scaled.
X_grid = X_grid.reshape((len(X_grid), 1))
plt.scatter(X, y, color = 'red')
plt.plot(X_grid, regressor.predict(X_grid), color = 'blue')
plt.title('Stochastic Load Estimation')
plt.xlabel('time')
plt.ylabel('load')
plt.show()