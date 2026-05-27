bool planHasFeature(Map<String, dynamic>? profile, String featureKey) {
  final features = profile?['planFeatures'];
  if (features is Map) {
    return features[featureKey] == true;
  }
  return false;
}
