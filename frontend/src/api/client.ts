import axios from 'axios';
import Constants from 'expo-constants';
import { Platform } from 'react-native';

const LOCAL_API_BASE_URL =
  Platform.OS === 'android'
    ? 'http://10.0.2.2:8000/api'
    : 'http://localhost:8000/api';

const API_BASE_URL = Constants.expoConfig?.extra?.apiBaseUrl || LOCAL_API_BASE_URL;

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;
