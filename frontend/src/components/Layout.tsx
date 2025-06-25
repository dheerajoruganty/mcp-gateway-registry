import React, { useState, Fragment } from 'react';
import { Menu, Transition } from '@headlessui/react';
import { Link } from 'react-router-dom';
import { 
  Bars3Icon, 
  UserIcon, 
  ChevronDownIcon,
  ArrowRightOnRectangleIcon,
  KeyIcon,
  Cog6ToothIcon,
  SunIcon,
  MoonIcon
} from '@heroicons/react/24/outline';
import Sidebar from './Sidebar';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import logo from '../assets/logo.png';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 overflow-hidden">
      {/* Header */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700">
        <div className="px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Left side */}
            <div className="flex items-center">
              {/* Sidebar toggle button - visible on all screen sizes */}
              <button
                type="button"
                className="p-2 rounded-md text-gray-400 hover:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-purple-500 mr-2"
                onClick={() => {
                  console.log('Toggle clicked, current state:', sidebarOpen);
                  setSidebarOpen(!sidebarOpen);
                }}
              >
                <Bars3Icon className="h-6 w-6" />
              </button>

              {/* Logo */}
              <div className="flex items-center ml-2 md:ml-0">
                <Link to="/" className="flex items-center hover:opacity-80 transition-opacity">
                  <img 
                    src={logo}
                    alt="MCP Gateway Logo" 
                    className="h-8 w-8 dark:brightness-0 dark:invert"
                  />
                  <span className="ml-2 text-xl font-bold text-gray-900 dark:text-white">
                    MCP Gateway
                  </span>
                </Link>
              </div>
            </div>

            {/* Right side */}
            <div className="flex items-center space-x-4">
              {/* Theme toggle */}
              <button
                onClick={toggleTheme}
                className="p-2 text-gray-400 hover:text-gray-500 dark:text-gray-300 dark:hover:text-gray-100 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                {theme === 'dark' ? (
                  <SunIcon className="h-5 w-5" />
                ) : (
                  <MoonIcon className="h-5 w-5" />
                )}
              </button>

              {/* User dropdown */}
              <Menu as="div" className="relative">
                <div>
                  <Menu.Button className="flex items-center space-x-3 text-sm rounded-full focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 p-2 hover:bg-gray-100 dark:hover:bg-gray-700">
                    <div className="h-8 w-8 rounded-full bg-purple-100 dark:bg-purple-800 flex items-center justify-center">
                      <UserIcon className="h-5 w-5 text-purple-600 dark:text-purple-300" />
                    </div>
                    <span className="hidden md:block text-gray-700 dark:text-gray-100 font-medium">
                      {user?.username || 'Admin'}
                    </span>
                    <ChevronDownIcon className="h-4 w-4 text-gray-400" />
                  </Menu.Button>
                </div>

                <Transition
                  as={Fragment}
                  enter="transition ease-out duration-100"
                  enterFrom="transform opacity-0 scale-95"
                  enterTo="transform opacity-100 scale-100"
                  leave="transition ease-in duration-75"
                  leaveFrom="transform opacity-100 scale-100"
                  leaveTo="transform opacity-0 scale-95"
                >
                  <Menu.Items className="absolute right-0 z-10 mt-2 w-48 origin-top-right rounded-md bg-white dark:bg-gray-800 py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/generate-token"
                          className={`${
                            active ? 'bg-gray-100 dark:bg-gray-800' : ''
                          } flex items-center px-4 py-2 text-sm text-gray-700 dark:text-gray-100`}
                        >
                          <KeyIcon className="mr-3 h-4 w-4" />
                          Generate Token
                        </Link>
                      )}
                    </Menu.Item>
                    
                    <Menu.Item>
                      {({ active }) => (
                        <Link
                          to="/settings"
                          className={`${
                            active ? 'bg-gray-100 dark:bg-gray-800' : ''
                          } flex items-center px-4 py-2 text-sm text-gray-700 dark:text-gray-100`}
                        >
                          <Cog6ToothIcon className="mr-3 h-4 w-4" />
                          Settings
                        </Link>
                      )}
                    </Menu.Item>

                    <div className="border-t border-gray-100 dark:border-gray-700 my-1" />
                    
                    <Menu.Item>
                      {({ active }) => (
                        <button
                          onClick={handleLogout}
                          className={`${
                            active ? 'bg-gray-100 dark:bg-gray-800' : ''
                          } flex items-center w-full px-4 py-2 text-sm text-gray-700 dark:text-gray-100`}
                        >
                          <ArrowRightOnRectangleIcon className="mr-3 h-4 w-4" />
                          Sign out
                        </button>
                      )}
                    </Menu.Item>
                  </Menu.Items>
                </Transition>
              </Menu>
            </div>
          </div>
        </div>
      </header>

      <div className="flex h-screen pt-16">
        {/* Sidebar */}
        <Sidebar sidebarOpen={sidebarOpen} setSidebarOpen={setSidebarOpen} />

        {/* Main content */}
        <main className={`flex-1 flex flex-col transition-all duration-300 ${
          sidebarOpen ? 'md:ml-64 lg:ml-72 xl:ml-80' : ''
        }`}>
          <div className="flex-1 flex flex-col px-4 sm:px-6 lg:px-8 py-4 md:py-8 overflow-hidden">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

export default Layout; 