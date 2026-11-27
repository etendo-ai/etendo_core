/*
 *************************************************************************
 * The contents of this file are subject to the Etendo License
 * (the "License"), you may not use this file except in compliance with
 * the License.
 * You may obtain a copy of the License at
 * https://github.com/etendosoftware/etendo_core/blob/main/legal/Etendo_license.txt
 * Software distributed under the License is distributed on an
 * "AS IS" basis, WITHOUT WARRANTY OF ANY KIND, either express or
 * implied. See the License for the specific language governing rights
 * and limitations under the License.
 * All portions are Copyright (C) 2026 FUTIT SERVICES, S.L
 * All Rights Reserved.
 * Contributor(s): Futit Services S.L.
 *************************************************************************
 */
package org.openbravo.service.json;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.logging.log4j.Level;
import org.apache.logging.log4j.core.Appender;
import org.apache.logging.log4j.core.LogEvent;
import org.apache.logging.log4j.core.LoggerContext;
import org.apache.logging.log4j.core.appender.AbstractAppender;
import org.apache.logging.log4j.core.config.Configuration;
import org.apache.logging.log4j.core.config.LoggerConfig;
import org.apache.logging.log4j.core.config.Property;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.openbravo.base.weld.test.WeldBaseTest;
import org.openbravo.dal.core.OBContext;

/** Checks the log emitted when adding or updating through {@link DefaultJsonDataService} fails. */
public class DefaultJsonDataServiceLoggingTest extends WeldBaseTest {

  private static final String VALID_CONTENT = "{\"data\":{\"_entityName\":\"BusinessPartnerCategory\"}}";
  private static final String ENTITY = "BusinessPartnerCategory";
  private static final String MARKER = "SECRET_CONTENT_MARKER";

  /** Sets the test user context, required to access the DAL. */
  @Before
  public void setTestContext() {
    setTestUserContext();
    OBContext.setAdminMode(false);
  }

  private Map<String, String> params(boolean withTabAndWindow) {
    Map<String, String> params = new HashMap<>();
    params.put(JsonConstants.ENTITYNAME, ENTITY);
    if (withTabAndWindow) {
      params.put(JsonConstants.TAB_PARAMETER, "TAB123");
      params.put(JsonConstants.WINDOW_ID, "WIN456");
    }
    return params;
  }

  // instantiated directly: the injected instance may be a subclass overriding update()
  private DefaultJsonDataService service;
  private List<String> errors = new ArrayList<>();
  private LoggerConfig loggerConfig;
  private Appender appender;

  /** Attaches an appender to a dedicated LoggerConfig of {@link DefaultJsonDataService}. */
  @Before
  public void attachAppender() {
    service = newService();
    errors = new ArrayList<>();
    final LoggerContext context = LoggerContext.getContext(false);
    final Configuration config = context.getConfiguration();
    appender = new AbstractAppender("DefaultJsonDataServiceLoggingTestAppender", null, null, true,
        Property.EMPTY_ARRAY) {
      @Override
      public void append(LogEvent event) {
        if (event.getLevel() == Level.ERROR) {
          errors.add(event.getMessage().getFormattedMessage());
        }
      }
    };
    appender.start();
    config.addAppender(appender);
    loggerConfig = new LoggerConfig(DefaultJsonDataService.class.getName(), Level.ERROR, false);
    loggerConfig.addAppender(appender, Level.ERROR, null);
    config.addLogger(DefaultJsonDataService.class.getName(), loggerConfig);
    context.updateLoggers();
  }

  /** Removes the appender and the LoggerConfig added by the test. */
  @After
  public void detachAppender() {
    OBContext.restorePreviousMode();
    final LoggerContext context = LoggerContext.getContext(false);
    final Configuration config = context.getConfiguration();
    config.removeLogger(DefaultJsonDataService.class.getName());
    loggerConfig.removeAppender(appender.getName());
    config.getAppenders().remove(appender.getName());
    context.updateLoggers();
    appender.stop();
  }

  /** A fresh service with the injected extra actions of the CDI managed instance. */
  private static DefaultJsonDataService newService() {
    try {
      DefaultJsonDataService managed = DefaultJsonDataService.getInstance();
      DefaultJsonDataService fresh = new DefaultJsonDataService();
      for (java.lang.reflect.Field field : DefaultJsonDataService.class.getDeclaredFields()) {
        if (!java.lang.reflect.Modifier.isStatic(field.getModifiers())) {
          field.setAccessible(true);
          field.set(fresh, field.get(managed));
        }
      }
      return fresh;
    } catch (IllegalAccessException e) {
      throw new IllegalStateException(e);
    }
  }

  private String firstErrorMessage(String prefix) {
    for (String message : errors) {
      if (message.startsWith(prefix)) {
        return message;
      }
    }
    throw new AssertionError("No error message with prefix " + prefix + " in " + errors);
  }

  private static final String CAUSE_CLASS = "org.postgresql.util.PSQLException";
  private static final String CAUSE_MESSAGE = "violates not-null constraint";

  private void assertLogsEntityTabWindowAndCause(String message) {
    assertTrue(message, message.contains("entity: " + ENTITY));
    assertTrue(message, message.contains("tabId: TAB123"));
    assertTrue(message, message.contains("windowId: WIN456"));
    assertTrue(message, message.contains(CAUSE_CLASS + ": "));
    assertTrue(message, message.contains(CAUSE_MESSAGE));
  }

  /** A failing add logs entity, tab, window and the cause class and message. */
  @Test
  public void failedAddLogsEntityTabWindowAndCause() {
    String response = service.add(params(true), VALID_CONTENT);
    assertLogsEntityTabWindowAndCause(firstErrorMessage("Error adding new object"));
    assertTrue(response, response.contains("error"));
  }

  /** A failing update logs entity, tab, window and the cause class and message. */
  @Test
  public void failedUpdateLogsEntityTabWindowAndCause() {
    service.update(params(true), VALID_CONTENT);
    assertLogsEntityTabWindowAndCause(firstErrorMessage("Error updating object"));
  }

  /** The request content is never logged. */
  @Test
  public void failedAddDoesNotLogContent() {
    service.add(params(true),
        "{\"data\":{\"_entityName\":\"" + ENTITY + "\",\"name\":\"" + MARKER + "\"}}");
    String message = firstErrorMessage("Error adding new object");
    assertFalse(message, message.contains(MARKER));
  }

  /** Missing tab and window do not break the logging nor the response. */
  @Test
  public void failedAddWithoutTabAndWindowStillLogs() {
    String response = service.add(params(false), VALID_CONTENT);
    String message = firstErrorMessage("Error adding new object");
    assertTrue(message, message.contains("entity: " + ENTITY));
    assertTrue(message, message.contains(CAUSE_MESSAGE));
    assertTrue(response, response.contains("error"));
  }
}
