// Don't use the shared rules that include asset-relocator-loader
// which injects __dirname references

module.exports = {
  module: {
    rules: [
      {
        test: /\.css$/,
        use: [{ loader: 'style-loader' }, { loader: 'css-loader' }],
      },
    ],
  },
  target: 'web',
};
