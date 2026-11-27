package org.openbravo.scheduling;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.servlet.ServletException;
import org.apache.logging.log4j.Level;
import org.apache.logging.log4j.core.Appender;
import org.apache.logging.log4j.core.LogEvent;
import org.apache.logging.log4j.core.LoggerContext;
import org.apache.logging.log4j.core.appender.AbstractAppender;
import org.apache.logging.log4j.core.config.Configuration;
import org.apache.logging.log4j.core.config.LoggerConfig;
import org.apache.logging.log4j.core.config.Property;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.mockito.Mock;
import org.mockito.MockedStatic;
import org.mockito.MockitoAnnotations;
import org.mockito.junit.MockitoJUnitRunner;
import org.openbravo.base.ConnectionProviderContextListener;
import org.openbravo.database.ConnectionProvider;
import org.openbravo.database.SessionInfo;
import org.openbravo.erpCommon.utility.SequenceIdData;
import org.openbravo.model.ad.ui.ProcessRun;
import org.quartz.Job;
import org.quartz.JobDataMap;
import org.quartz.JobExecutionContext;
import org.quartz.Scheduler;
import org.quartz.SchedulerContext;
import org.quartz.SchedulerException;
import org.quartz.Trigger;

/**
 * Test class for ProcessMonitor functionality.
 * Tests job execution veto logic and duration formatting.
 */
@RunWith(MockitoJUnitRunner.class)
public class ProcessMonitorTest {

  private ProcessMonitor processMonitor;

  @Mock
  private SchedulerContext schedulerContext;

  @Mock
  private Trigger trigger;

  @Mock
  private JobDataMap jobDataMap;

  @Mock
  private JobExecutionContext jobExecutionContext;

  @Mock
  private Scheduler scheduler;

  /**
   * Sets up the test environment before each test.
   * Initialize mocks and configures common trigger setup.
   *
   * @throws Exception if there's an error initializing the mocks or configuring the trigger
   */
  @Before
  public void setUp() throws Exception {
    MockitoAnnotations.openMocks(this);

    // Setup the ProcessMonitor
    processMonitor = new ProcessMonitor("TestMonitor", schedulerContext);

    // Common trigger setup
    when(trigger.getJobDataMap()).thenReturn(jobDataMap);
  }

  /**
   * Tests that job execution is not vetoed when concurrent executions are allowed.
   */
  @Test
  public void testVetoJobExecutionWithNoPreventConcurrentExecutions() {
    // Arrange
    when(jobDataMap.get(Process.PREVENT_CONCURRENT_EXECUTIONS)).thenReturn(false);

    // Act
    boolean result = processMonitor.vetoJobExecution(trigger, jobExecutionContext);

    // Assert
    assertFalse(result);
  }

  /**
   * Tests that job execution is not vetoed when there are no concurrent jobs running.
   *
   * @throws SchedulerException if there's an error accessing the scheduler
   *         or retrieving currently executing jobs
   */
  @Test
  public void testVetoJobExecutionWithPreventConcurrentExecutionsNoConcurrentJobs() throws SchedulerException {
    // Arrange
    when(jobDataMap.get(Process.PREVENT_CONCURRENT_EXECUTIONS)).thenReturn(true);
    when(jobDataMap.getString(Process.PROCESS_NAME)).thenReturn("TestProcess");
    when(jobDataMap.get(Process.PROCESS_ID)).thenReturn("TestProcessId");

    List<JobExecutionContext> emptyJobsList = new ArrayList<>();
    when(jobExecutionContext.getScheduler()).thenReturn(scheduler);
    when(scheduler.getCurrentlyExecutingJobs()).thenReturn(emptyJobsList);

    // Act
    boolean result = processMonitor.vetoJobExecution(trigger, jobExecutionContext);

    // Assert
    assertFalse(result);
  }

  /**
   * Tests that the monitor name is correctly returned.
   */
  @Test
  public void testGetName() {
    // Act
    String name = processMonitor.getName();

    // Assert
    assertEquals("TestMonitor", name);
  }

  /**
   * Tests the duration formatting for a typical duration value.
   */
  @Test
  public void testGetDuration() {
    // Arrange
    long duration = 3723456;

    // Act
    String result = ProcessMonitor.getDuration(duration);

    // Assert
    assertEquals("01:02:03.456", result);
  }

  /**
   * Tests the duration formatting for small duration values.
   * Verifies correct padding of zeros for milliseconds, seconds, and minutes.
   */
  @Test
  public void testGetDurationSmallValues() {
    // Arrange & Act & Assert
    assertEquals("00:00:01.005", ProcessMonitor.getDuration(1005));
    assertEquals("00:00:01.050", ProcessMonitor.getDuration(1050));
    assertEquals("00:00:01.005", ProcessMonitor.getDuration(1005));
    assertEquals("00:00:00.005", ProcessMonitor.getDuration(5));
  }

  /** Helper running jobWasExecuted with the static collaborators mocked. */
  private void runJobWasExecuted(MockedStatic<ProcessBundle> bundleStatic, GroupInfo groupInfo) {
    ProcessBundle bundle = mock(ProcessBundle.class);
    ProcessContext ctx = mock(ProcessContext.class);
    when(ctx.getUser()).thenReturn("100");
    when(bundle.getContext()).thenReturn(ctx);
    when(bundle.getGroupInfo()).thenReturn(groupInfo);
    Map<String, Object> map = new HashMap<>();
    JobDataMap merged = mock(JobDataMap.class);
    when(merged.get(ProcessBundle.KEY)).thenReturn(map);
    bundleStatic.when(() -> ProcessBundle.mapToObject(any())).thenReturn(bundle);
    JobExecutionContext jec = mock(JobExecutionContext.class);
    when(jec.getMergedJobDataMap()).thenReturn(merged);
    when(jec.get(Process.EXECUTION_ID)).thenReturn("exec1");
    when(jec.getJobInstance()).thenReturn(mock(Job.class));
    when(jec.getTrigger()).thenReturn(trigger);
    when(jobDataMap.getString(Process.PROCESS_NAME)).thenReturn("MyProc");
    when(schedulerContext.get(ConnectionProviderContextListener.POOL_ATTRIBUTE))
        .thenReturn(mock(ConnectionProvider.class));
    processMonitor.jobWasExecuted(jec, null);
  }

  /** The normal path updates the process run once and does not discard the connection. */
  @Test
  public void jobWasExecutedHappyPathUpdatesOnce() {
    try (MockedStatic<ProcessRunData> runData = mockStatic(ProcessRunData.class);
        MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      runJobWasExecuted(bundleStatic, null);
      runData.verify(() -> ProcessRunData.update(any(), anyString(), eq(Process.SUCCESS),
          anyString(), any(), eq("exec1")), times(1));
      sessionInfo.verify(SessionInfo::discardSessionConnection, never());
      sessionInfo.verify(SessionInfo::init, times(1));
    }
  }

  /** A failing update is retried once on a new connection and then succeeds. */
  @Test
  public void jobWasExecutedRetriesOnceAfterServletException() {
    try (MockedStatic<ProcessRunData> runData = mockStatic(ProcessRunData.class);
        MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      runData
          .when(() -> ProcessRunData.update(any(), anyString(), anyString(), anyString(), any(),
              anyString()))
          .thenThrow(new ServletException("I/O error"))
          .thenReturn(1);
      runJobWasExecuted(bundleStatic, null);
      runData.verify(() -> ProcessRunData.update(any(), anyString(), anyString(), anyString(),
          any(), anyString()), times(2));
      sessionInfo.verify(SessionInfo::discardSessionConnection, times(1));
      sessionInfo.verify(SessionInfo::init, times(1));
    }
  }

  /** If the retry also fails there are exactly two attempts and the connection is released. */
  @Test
  public void jobWasExecutedDoubleFailureReleasesConnection() {
    try (MockedStatic<ProcessRunData> runData = mockStatic(ProcessRunData.class);
        MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      runData
          .when(() -> ProcessRunData.update(any(), anyString(), anyString(), anyString(), any(),
              anyString()))
          .thenThrow(new ServletException("I/O error"));
      List<String> errors = captureErrors(() -> runJobWasExecuted(bundleStatic, null));
      runData.verify(() -> ProcessRunData.update(any(), anyString(), anyString(), anyString(),
          any(), anyString()), times(2));
      sessionInfo.verify(SessionInfo::init, times(1));
      assertEquals(errors.toString(), 1, errors.size());
      assertTrue(errors.get(0), errors.get(0).contains("MyProc"));
      assertTrue(errors.get(0), errors.get(0).contains("exec1"));
    }
  }

  /** No error is logged when the retry succeeds. */
  @Test
  public void jobWasExecutedRetrySuccessLogsNoError() {
    try (MockedStatic<ProcessRunData> runData = mockStatic(ProcessRunData.class);
        MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      runData
          .when(() -> ProcessRunData.update(any(), anyString(), anyString(), anyString(), any(),
              anyString()))
          .thenThrow(new ServletException("I/O error"))
          .thenReturn(1);
      List<String> errors = captureErrors(() -> runJobWasExecuted(bundleStatic, null));
      assertTrue(errors.toString(), errors.isEmpty());
    }
  }

  /**
   * The group close is retried once, while the next process of the group is executed only once.
   */
  @Test
  public void manageGroupRetriesGroupCloseButNotNextProcess() throws Exception {
    try (MockedStatic<ProcessRunData> runData = mockStatic(ProcessRunData.class);
        MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      GroupInfo groupInfo = mock(GroupInfo.class);
      ProcessRun groupRun = mock(ProcessRun.class);
      when(groupRun.getId()).thenReturn("grp1");
      when(groupInfo.getProcessRun()).thenReturn(groupRun);
      when(groupInfo.executeNextProcess()).thenReturn(GroupInfo.END);
      when(groupInfo.getStatus()).thenReturn(Process.SUCCESS);
      runData
          .when(() -> ProcessRunData.update(any(), anyString(), anyString(), anyString(), any(),
              eq("grp1")))
          .thenThrow(new ServletException("I/O error"))
          .thenReturn(1);
      runJobWasExecuted(bundleStatic, groupInfo);
      runData.verify(() -> ProcessRunData.update(any(), anyString(), anyString(), anyString(),
          any(), eq("grp1")), times(2));
      runData.verify(() -> ProcessRunData.updateGroup(any(), eq("grp1"), eq("exec1")), times(1));
      verify(groupInfo, times(1)).executeNextProcess();
      sessionInfo.verify(SessionInfo::discardSessionConnection, times(1));
    }
  }

  /** Runs the action collecting the ERROR messages logged by {@link ProcessMonitor}. */
  private List<String> captureErrors(Runnable action) {
    final List<String> errors = new ArrayList<>();
    LoggerContext context = LoggerContext.getContext(false);
    Configuration config = context.getConfiguration();
    Appender appender = new AbstractAppender("ProcessMonitorTestAppender", null, null, true,
        Property.EMPTY_ARRAY) {
      @Override
      public void append(LogEvent event) {
        if (event.getLevel() == Level.ERROR
            && ProcessMonitor.class.getName().equals(event.getLoggerName())) {
          errors.add(event.getMessage().getFormattedMessage());
        }
      }
    };
    appender.start();
    // dedicated LoggerConfig, so the root configuration is never touched
    LoggerConfig loggerConfig = new LoggerConfig(ProcessMonitor.class.getName(), Level.ERROR,
        false);
    config.addAppender(appender);
    loggerConfig.addAppender(appender, Level.ERROR, null);
    config.addLogger(ProcessMonitor.class.getName(), loggerConfig);
    context.updateLoggers();
    try {
      action.run();
    } finally {
      config.removeLogger(ProcessMonitor.class.getName());
      loggerConfig.removeAppender(appender.getName());
      config.getAppenders().remove(appender.getName());
      context.updateLoggers();
      appender.stop();
    }
    return errors;
  }

  /** The thread connection is validated and the update is executed once. */
  @Test
  public void jobWasExecutedValidatesConnectionBeforeUpdating() {
    try (MockedStatic<ProcessRunData> runData = mockStatic(ProcessRunData.class);
        MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      runJobWasExecuted(bundleStatic, null);
      sessionInfo.verify(() -> SessionInfo.discardSessionConnectionIfInvalid(5), times(1));
      runData.verify(() -> ProcessRunData.update(any(), anyString(), anyString(), anyString(),
          any(), anyString()), times(1));
    }
  }

  /** The connection is released when registering a misfire fails. */
  @Test
  public void triggerMisfiredReleasesConnectionOnFailure() {
    try (MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      bundleStatic.when(() -> ProcessBundle.mapToObject(any()))
          .thenThrow(new IllegalStateException("boom"));
      processMonitor.triggerMisfired(trigger);
      sessionInfo.verify(SessionInfo::init, times(1));
    }
  }

  /** The connection is validated before finalizing the trigger. */
  @Test
  public void triggerFinalizedDiscardsInvalidConnectionBeforeUpdate() {
    try (MockedStatic<ProcessRequestData> reqData = mockStatic(ProcessRequestData.class);
        MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      bundleStatic.when(() -> ProcessBundle.mapToObject(any())).thenReturn(null);
      when(trigger.getKey()).thenReturn(new org.quartz.TriggerKey("t"));
      when(schedulerContext.get(ConnectionProviderContextListener.POOL_ATTRIBUTE))
          .thenReturn(mock(ConnectionProvider.class));
      processMonitor.triggerFinalized(trigger);
      sessionInfo.verify(() -> SessionInfo.discardSessionConnectionIfInvalid(5), times(1));
      reqData.verify(() -> ProcessRequestData.update(any(), anyString(), anyString(), anyString()),
          times(1));
      sessionInfo.verify(SessionInfo::init, times(1));
    }
  }

  /** A concurrent process group attempt validates the connection and releases it afterwards. */
  @Test
  public void stopConcurrencyValidatesAndReleasesConnection() throws Exception {
    try (MockedStatic<ProcessRunData> runData = mockStatic(ProcessRunData.class);
        MockedStatic<SessionInfo> sessionInfo = mockStatic(SessionInfo.class);
        MockedStatic<SequenceIdData> sequence = mockStatic(SequenceIdData.class);
        MockedStatic<ProcessBundle> bundleStatic = mockStatic(ProcessBundle.class)) {
      ProcessBundle bundle = mock(ProcessBundle.class);
      ProcessContext ctx = mock(ProcessContext.class);
      when(bundle.getContext()).thenReturn(ctx);
      bundleStatic.when(() -> ProcessBundle.mapToObject(any())).thenReturn(bundle);
      sequence.when(SequenceIdData::getUUID).thenReturn("exec1");
      runData.when(() -> ProcessRunData.selectConcurrent(any(), any())).thenReturn("1");
      when(jobDataMap.get(Process.PREVENT_CONCURRENT_EXECUTIONS)).thenReturn(true);
      when(jobDataMap.getString(Process.PROCESS_NAME)).thenReturn("MyProc");
      when(jobDataMap.get(Process.PROCESS_ID)).thenReturn(GroupInfo.processGroupId);
      when(jobExecutionContext.getScheduler()).thenReturn(scheduler);
      when(scheduler.getCurrentlyExecutingJobs()).thenReturn(new ArrayList<>());
      when(jobExecutionContext.getMergedJobDataMap()).thenReturn(jobDataMap);
      when(trigger.mayFireAgain()).thenReturn(true);
      when(trigger.getKey()).thenReturn(new org.quartz.TriggerKey("t"));
      when(schedulerContext.get(ConnectionProviderContextListener.POOL_ATTRIBUTE))
          .thenReturn(mock(ConnectionProvider.class));

      assertTrue(processMonitor.vetoJobExecution(trigger, jobExecutionContext));

      sessionInfo.verify(() -> SessionInfo.discardSessionConnectionIfInvalid(5), times(1));
      runData.verify(() -> ProcessRunData.update(any(), any(), eq(Process.ERROR), any(), any(), eq("exec1")),
          times(1));
      sessionInfo.verify(SessionInfo::init, times(1));
    }
  }
}
